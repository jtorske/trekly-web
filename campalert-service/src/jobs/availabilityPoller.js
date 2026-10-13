"use strict";

const cron = require("node-cron");
const pcClient = require("../api/parksCanadaClient");
const pool = require("../db/pool");
const { notificationsQueue } = require("../queue");

const JITTER_MIN_SECONDS = 30;
const JITTER_MAX_SECONDS = 60;
// Not a confirmed API limit — just a safety cap so one alert with a wide
// arrival-date spread can't silently balloon a poll into a huge date range.
const MAX_POLL_WINDOW_DAYS = 90;

function addDays(dateStr, days) {
  const d = new Date(`${dateStr}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function diffDays(a, b) {
  return Math.round((new Date(`${b}T00:00:00Z`) - new Date(`${a}T00:00:00Z`)) / 86400000);
}

/**
 * Step 1: figure out which campgrounds actually need polling this cycle,
 * and the single date window that covers every active alert on that
 * campground — the union of each alert's [arrival_date, arrival_date +
 * nights - 1] span. One call per campground, not one per alert, per the
 * cost requirement.
 */
async function computeCampgroundWindows() {
  const [alerts] = await pool.query(
    `SELECT campground_id, arrival_dates, nights FROM alerts WHERE active = TRUE`,
  );

  const windows = new Map(); // campground_id -> { minDate, maxDate }
  for (const alert of alerts) {
    const dates = Array.isArray(alert.arrival_dates)
      ? alert.arrival_dates
      : JSON.parse(alert.arrival_dates);

    for (const date of dates) {
      const end = addDays(date, alert.nights - 1);
      const existing = windows.get(alert.campground_id);
      if (!existing) {
        windows.set(alert.campground_id, { minDate: date, maxDate: end });
      } else {
        if (date < existing.minDate) existing.minDate = date;
        if (end > existing.maxDate) existing.maxDate = end;
      }
    }
  }

  for (const [campgroundId, w] of windows) {
    const span = diffDays(w.minDate, w.maxDate);
    if (span > MAX_POLL_WINDOW_DAYS) {
      console.warn(
        `availabilityPoller: campground ${campgroundId} alert date span is ${span} days — ` +
          `clipping to ${MAX_POLL_WINDOW_DAYS} days from the earliest date (safety cap, not a confirmed API limit).`,
      );
      w.maxDate = addDays(w.minDate, MAX_POLL_WINDOW_DAYS);
    }
  }

  return windows;
}

/**
 * Scope-lock: only ever pulls sites explicitly marked is_backcountry = TRUE
 * for this campground, enforced at the query level — not inferred from
 * "catalogSync only syncs backcountry data".
 */
async function getCampgroundBackcountrySites(campgroundId) {
  const [rows] = await pool.query(
    `SELECT s.id, s.pc_resource_id, s.name, s.map_id, c.pc_resource_location_id
     FROM sites s
     JOIN campgrounds c ON c.id = s.campground_id
     WHERE s.campground_id = ? AND s.is_backcountry = TRUE`,
    [campgroundId],
  );
  return rows;
}

async function fetchExistingSnapshots(siteIds, startDate, endDate) {
  if (siteIds.length === 0) return new Map();
  const [rows] = await pool.query(
    `SELECT site_id, date, status FROM availability_snapshots
     WHERE site_id IN (?) AND date BETWEEN ? AND ?`,
    [siteIds, startDate, endDate],
  );
  const map = new Map();
  for (const row of rows) {
    const dateStr = row.date instanceof Date ? row.date.toISOString().slice(0, 10) : row.date;
    map.set(`${row.site_id}|${dateStr}`, row.status);
  }
  return map;
}

async function upsertSnapshotsBulk(snapshotRows) {
  if (snapshotRows.length === 0) return;
  const values = [];
  const placeholders = snapshotRows
    .map((r) => {
      values.push(r.siteId, r.date, r.status, r.checkedAt);
      return "(?, ?, ?, ?)";
    })
    .join(", ");
  await pool.query(
    `INSERT INTO availability_snapshots (site_id, date, status, checked_at)
     VALUES ${placeholders}
     ON DUPLICATE KEY UPDATE status = VALUES(status), checked_at = VALUES(checked_at)`,
    values,
  );
}

/**
 * Polls one (campground, mapId) group, diffs against the last stored
 * snapshot per site+date, and updates every snapshot regardless of whether
 * a transition was found — per spec, the cache always reflects the latest
 * poll. Returns the list of genuine 0->1 transitions found.
 *
 * A first-ever observation of a site+date (no prior snapshot row) is never
 * treated as a transition, even if it comes back available — only a
 * confirmed prior 0 flipping to 1 counts. This matches "on any 0 -> 1
 * transition" literally; the practical effect is a brand-new alert whose
 * target is already open won't get an immediate notification, only future
 * re-opens after a booked spell. Worth knowing, not obviously wrong.
 */
async function pollMapGroup({ campgroundId, resourceLocationId, mapId, sites, startDate, endDate }) {
  let availability;
  try {
    availability = await pcClient.getAvailabilityMap({
      mapId,
      resourceLocationId,
      startDate,
      endDate,
    });
  } catch (err) {
    // parksCanadaClient already retried with exponential backoff before
    // throwing — this is a final failure, skip just this group.
    console.error(
      `availabilityPoller: campground=${campgroundId} mapId=${mapId} failed after retries: ` +
        `${err.message} — skipping this group this cycle.`,
    );
    return [];
  }

  const siteIds = sites.map((s) => s.id);
  const existing = await fetchExistingSnapshots(siteIds, startDate, endDate);

  const now = new Date();
  const snapshotRows = [];
  const transitions = [];

  for (const site of sites) {
    const nights = availability?.resourceAvailabilities?.[site.pc_resource_id];
    if (!nights || nights.length === 0) continue;

    nights.forEach((night, index) => {
      const date = addDays(startDate, index);
      const oldStatus = existing.get(`${site.id}|${date}`);
      const newStatus = night.availability;

      snapshotRows.push({ siteId: site.id, date, status: newStatus, checkedAt: now });

      if (oldStatus === 0 && newStatus === 1) {
        transitions.push({ siteId: site.id, date });
      }
    });
  }

  await upsertSnapshotsBulk(snapshotRows);

  return transitions;
}

async function isBackcountrySite(siteId) {
  const [rows] = await pool.query(
    `SELECT 1 FROM sites WHERE id = ? AND is_backcountry = TRUE LIMIT 1`,
    [siteId],
  );
  return rows.length > 0;
}

async function checkConsecutiveNightsAvailable(siteId, startDate, nights) {
  const endDate = addDays(startDate, nights - 1);
  const [rows] = await pool.query(
    `SELECT date, status FROM availability_snapshots WHERE site_id = ? AND date BETWEEN ? AND ?`,
    [siteId, startDate, endDate],
  );
  if (rows.length < nights) return false; // missing data for at least one required night
  return rows.every((r) => r.status === 1);
}

/**
 * For one 0->1 transition, finds every active alert on this campground that
 * requested this exact arrival date, and checks whether the opening
 * actually covers that alert's requested `nights` consecutively (not just
 * the single night that flipped). Accumulates matches into openingsByAlert
 * so the caller can send one batched email per alert, not one per opening.
 */
async function matchAlertsForTransition({ siteId, date, campgroundId, siteName }, openingsByAlert) {
  // Scope-lock re-checked here too, not just trusted from the caller's
  // query — belt and suspenders per the "even indirectly" requirement.
  if (!(await isBackcountrySite(siteId))) return;

  const [alerts] = await pool.query(
    `SELECT id, nights FROM alerts
     WHERE campground_id = ? AND active = TRUE AND JSON_CONTAINS(arrival_dates, JSON_QUOTE(?))`,
    [campgroundId, date],
  );

  for (const alert of alerts) {
    const satisfied = await checkConsecutiveNightsAvailable(siteId, date, alert.nights);
    if (!satisfied) continue;

    if (!openingsByAlert.has(alert.id)) openingsByAlert.set(alert.id, []);
    openingsByAlert.get(alert.id).push({ siteId, siteName, date, nights: alert.nights });
  }
}

async function runAvailabilityPoller() {
  console.log("availabilityPoller: starting run");

  const windows = await computeCampgroundWindows();
  if (windows.size === 0) {
    console.log("availabilityPoller: no active alerts — nothing to poll");
    return;
  }

  const openingsByAlert = new Map();

  for (const [campgroundId, { minDate, maxDate }] of windows) {
    const sites = await getCampgroundBackcountrySites(campgroundId);
    const pollable = sites.filter((s) => s.map_id !== null);
    const skipped = sites.length - pollable.length;
    if (skipped > 0) {
      console.warn(
        `availabilityPoller: campground ${campgroundId} has ${skipped} backcountry site(s) ` +
          "with no known map_id — can't poll those, skipping just them.",
      );
    }
    if (pollable.length === 0) continue;

    const resourceLocationId = pollable[0].pc_resource_location_id;

    const byMapId = new Map();
    for (const site of pollable) {
      if (!byMapId.has(site.map_id)) byMapId.set(site.map_id, []);
      byMapId.get(site.map_id).push(site);
    }

    for (const [mapId, mapSites] of byMapId) {
      const transitions = await pollMapGroup({
        campgroundId,
        resourceLocationId,
        mapId,
        sites: mapSites,
        startDate: minDate,
        endDate: maxDate,
      });

      const nameById = new Map(mapSites.map((s) => [s.id, s.name]));
      for (const t of transitions) {
        await matchAlertsForTransition(
          { ...t, campgroundId, siteName: nameById.get(t.siteId) },
          openingsByAlert,
        );
      }
    }
  }

  for (const [alertId, openings] of openingsByAlert) {
    await notificationsQueue.add("alert-notification", { alertId, openings });
    console.log(
      `availabilityPoller: enqueued notification for alert ${alertId} — ${openings.length} opening(s)`,
    );
  }

  console.log(
    `availabilityPoller: run complete — polled ${windows.size} campground(s), ` +
      `${openingsByAlert.size} alert(s) matched`,
  );
}

function schedule() {
  const cronExpression = process.env.AVAILABILITY_POLL_CRON ?? "*/5 * * * *";
  cron.schedule(cronExpression, () => {
    const jitterMs =
      (JITTER_MIN_SECONDS + Math.random() * (JITTER_MAX_SECONDS - JITTER_MIN_SECONDS)) * 1000;
    setTimeout(() => {
      runAvailabilityPoller().catch((err) =>
        console.error("availabilityPoller: scheduled run failed:", err),
      );
    }, jitterMs);
  });
  console.log(
    `availabilityPoller: scheduled with cron expression "${cronExpression}" ` +
      `(+${JITTER_MIN_SECONDS}-${JITTER_MAX_SECONDS}s jitter)`,
  );
}

module.exports = { runAvailabilityPoller, schedule, computeCampgroundWindows };

// One-off manual run: `node src/jobs/availabilityPoller.js`
if (require.main === module) {
  runAvailabilityPoller()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error(err);
      process.exit(1);
    });
}
