"use strict";

const cron = require("node-cron");
const pcClient = require("../api/parksCanadaClient");
const pool = require("../db/pool");

const BACKCOUNTRY_MARKER_EN = "Backcountry";

// availability===3 is a static per-site property that never varies by
// date (confirmed) — a short probe window is enough to detect it, no need
// to scan the whole booking horizon. Kept short to minimize load against
// reservation.pc.gc.ca during a catalog sync.
const AVAILABILITY_PROBE_NIGHTS = 3;

function isoDate(offsetDays = 0) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

/**
 * Step 1-2: fetch every resourceLocation nationwide and filter to
 * backcountry ones that actually have a map. Matches Parks Canada's own
 * categorization (en-CA shortName/fullName containing "Backcountry")
 * rather than resourceCategoryIds, which aren't consistent across parks.
 * rootMapId: null locations (e.g. the "Internet" utility entry) are
 * non-campground entries and are dropped regardless of name.
 */
async function discoverBackcountryLocations() {
  const response = await pcClient.getResourceLocations();
  // Confirmed live: the response is a plain top-level array (114 entries),
  // not the { value: [...], Count } wrapper originally described. Handling
  // both shapes defensively rather than assuming either going forward,
  // since this is exactly the kind of detail that turned out different
  // from the spec once checked against a real response.
  const allLocations = Array.isArray(response) ? response : (response?.value ?? []);

  console.log(
    `catalogSync: fetched ${allLocations.length} resourceLocations` +
      (typeof response?.Count === "number" ? ` (API reported Count: ${response.Count})` : ""),
  );

  const matched = [];
  for (const location of allLocations) {
    if (location.rootMapId === null || location.rootMapId === undefined) continue;

    const localized = pcClient.findLocalizedValue(location.localizedValues, "en-CA");
    if (!localized) {
      console.warn(
        `catalogSync: resourceLocationId=${location.resourceLocationId} has no en-CA ` +
          "localizedValues entry (or the locale-key guess in parksCanadaClient is wrong) " +
          "— skipping, can't classify it. Worth checking a raw entry if this fires a lot.",
      );
      continue;
    }

    const shortName = localized.shortName ?? "";
    const fullName = localized.fullName ?? "";
    if (shortName.includes(BACKCOUNTRY_MARKER_EN) || fullName.includes(BACKCOUNTRY_MARKER_EN)) {
      matched.push({
        resourceLocationId: location.resourceLocationId,
        name: fullName || shortName,
      });
    }
  }

  // Sanity-check log per the ask: eyeball this against the ~12 backcountry
  // entries visible by name in the raw response before running unattended.
  console.log(`catalogSync: matched ${matched.length} backcountry locations:`);
  for (const loc of matched) {
    console.log(`  - [${loc.resourceLocationId}] ${loc.name}`);
  }

  return matched;
}

/**
 * Step 3-4: for one matched location, fetch its resources, keep only
 * resourceModel===2, then exclude any of those whose availability is
 * structurally always 3 (checked via a short live probe against
 * availability/map, grouped by mapId since that endpoint takes one map at
 * a time). Sites we can't get a clear read on are kept (not excluded) but
 * logged loudly — silently dropping a possibly-real bookable site is worse
 * than occasionally keeping one that turns out to be a dud.
 */
async function fetchBookableSites(location) {
  const resources = await pcClient.getResources(location.resourceLocationId);

  const candidates = [];
  for (const [resourceId, resource] of Object.entries(resources ?? {})) {
    if (resource.resourceModel !== 2) continue;

    const localized = pcClient.findLocalizedValue(resource.localizedValues, "en-CA");
    const name = localized?.name ?? `(unnamed resource ${resourceId})`;

    const mapIds = Array.isArray(resource.mapIds) ? resource.mapIds : [];
    if (mapIds.length === 0) {
      console.warn(
        `catalogSync: [${location.resourceLocationId}] resource ${resourceId} (${name}) has ` +
          "no mapIds — can't probe its availability, keeping it but flagging for review.",
      );
      candidates.push({ resourceId, name, mapId: null });
      continue;
    }
    if (mapIds.length > 1) {
      console.warn(
        `catalogSync: [${location.resourceLocationId}] resource ${resourceId} (${name}) has ` +
          `multiple mapIds (${mapIds.join(", ")}) — using the first, flagging for review.`,
      );
    }
    candidates.push({ resourceId, name, mapId: mapIds[0] });
  }

  // Group by mapId so each distinct map is probed once, not once per site.
  const byMapId = new Map();
  for (const candidate of candidates) {
    if (candidate.mapId === null) continue;
    if (!byMapId.has(candidate.mapId)) byMapId.set(candidate.mapId, []);
    byMapId.get(candidate.mapId).push(candidate);
  }

  const startDate = isoDate(0);
  const endDate = isoDate(AVAILABILITY_PROBE_NIGHTS);
  const bookable = [];

  for (const [mapId, sitesOnMap] of byMapId) {
    let availability;
    try {
      availability = await pcClient.getAvailabilityMap({
        mapId,
        resourceLocationId: location.resourceLocationId,
        startDate,
        endDate,
      });
    } catch (err) {
      console.warn(
        `catalogSync: [${location.resourceLocationId}] availability probe failed for ` +
          `mapId=${mapId}: ${err.message} — keeping its ${sitesOnMap.length} site(s) unfiltered, flagging for review.`,
      );
      bookable.push(...sitesOnMap);
      continue;
    }

    for (const site of sitesOnMap) {
      const nights = availability?.resourceAvailabilities?.[site.resourceId];
      if (!nights || nights.length === 0) {
        console.warn(
          `catalogSync: [${location.resourceLocationId}] no availability data for resource ` +
            `${site.resourceId} (${site.name}) under mapId=${mapId} — keeping it, flagging for review.`,
        );
        bookable.push(site);
        continue;
      }

      const alwaysThree = nights.every((night) => night.availability === 3);
      if (alwaysThree) {
        console.log(
          `catalogSync: excluding ${site.resourceId} (${site.name}) — availability===3 across ` +
            "the whole probe window (not bookable via this API).",
        );
        continue;
      }

      bookable.push(site);
    }
  }

  // Sites with no mapId at all never went through a map group above.
  for (const candidate of candidates) {
    if (candidate.mapId === null) bookable.push(candidate);
  }

  return bookable;
}

async function upsertCampground({ resourceLocationId, name }) {
  const [result] = await pool.query(
    `INSERT INTO campgrounds (pc_resource_location_id, name, last_synced_at)
     VALUES (?, ?, NOW())
     ON DUPLICATE KEY UPDATE
       name = VALUES(name),
       last_synced_at = VALUES(last_synced_at),
       id = LAST_INSERT_ID(id)`,
    [resourceLocationId, name],
  );
  return result.insertId;
}

async function upsertSite(campgroundId, site) {
  await pool.query(
    `INSERT INTO sites (campground_id, pc_resource_id, name, resource_model, is_backcountry, map_id, last_synced_at)
     VALUES (?, ?, ?, 2, TRUE, ?, NOW())
     ON DUPLICATE KEY UPDATE
       name = VALUES(name),
       resource_model = VALUES(resource_model),
       is_backcountry = VALUES(is_backcountry),
       map_id = VALUES(map_id),
       last_synced_at = VALUES(last_synced_at)`,
    [campgroundId, site.resourceId, site.name, site.mapId ?? null],
  );
}

async function runCatalogSync() {
  console.log("catalogSync: starting run");

  const locations = await discoverBackcountryLocations();

  let totalSites = 0;
  for (const location of locations) {
    let sites;
    try {
      sites = await fetchBookableSites(location);
    } catch (err) {
      console.error(
        `catalogSync: failed to sync location [${location.resourceLocationId}] ${location.name}: ${err.message}`,
      );
      continue;
    }

    const campgroundId = await upsertCampground(location);
    for (const site of sites) {
      await upsertSite(campgroundId, site);
    }

    console.log(
      `catalogSync: [${location.resourceLocationId}] ${location.name} — ${sites.length} bookable site(s) synced`,
    );
    totalSites += sites.length;
  }

  console.log(
    `catalogSync: run complete — ${locations.length} backcountry location(s), ${totalSites} bookable site(s) total`,
  );
}

function schedule() {
  const cronExpression = process.env.CATALOG_SYNC_CRON ?? "0 6 * * *";
  cron.schedule(cronExpression, () => {
    runCatalogSync().catch((err) => console.error("catalogSync: scheduled run failed:", err));
  });
  console.log(`catalogSync: scheduled with cron expression "${cronExpression}"`);
}

module.exports = { runCatalogSync, discoverBackcountryLocations, fetchBookableSites, schedule };

// Allows a one-off manual run for sanity-checking before wiring this into
// index.js: `node src/jobs/catalogSync.js` (env vars are loaded by
// src/db/pool.js as soon as it's required, above)
if (require.main === module) {
  runCatalogSync()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error(err);
      process.exit(1);
    });
}
