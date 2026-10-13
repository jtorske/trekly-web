"use strict";

/**
 * Client for the (undocumented, reverse-engineered) Parks Canada
 * reservation API. Every detail baked in here — headers, param shapes,
 * the fact that cart/booking UIDs are throwaway — comes from manual
 * reverse-engineering against https://reservation.pc.gc.ca, not the
 * public docs (there aren't any).
 *
 * Requires Node 18+ for global fetch/crypto.randomUUID.
 */

const crypto = require("node:crypto");

const BASE_URL = "https://reservation.pc.gc.ca/api";
const RESULTS_PAGE_URL = "https://reservation.pc.gc.ca/create-booking/results";

const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";

// Confirmed required — omitting these gets a 403 regardless of the params
// being otherwise correct.
const BASE_HEADERS = {
  "User-Agent": USER_AGENT,
  Accept: "application/json, text/plain, */*",
  "Accept-Language": "en-CA,en;q=0.9",
};

const DEFAULT_BOOKING_CATEGORY_ID = 7;
const DEFAULT_NUM_EQUIPMENT = 2;
// Matches the confirmed peopleCapacityCategoryCounts example exactly:
// one "standard" capacity category (-32767), party of 2.
const DEFAULT_PEOPLE_CAPACITY_CATEGORY_COUNTS = [
  { capacityCategoryId: -32767, subCapacityCategoryId: null, count: 2 },
];

const MAX_RETRIES = 4;
const BASE_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 8000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Exponential backoff with jitter, capped at MAX_BACKOFF_MS. Retries on
 * *any* non-2xx or network error, not just 5xx/429 — this API is
 * undocumented and has been observed to intermittently 403/blip under
 * normal use, and a bounded retry (4 attempts, ~500ms-8s spacing) is cheap
 * insurance against that. A request that's genuinely malformed will still
 * fail after MAX_RETRIES, just a few seconds slower.
 */
async function requestWithRetry(url, extraHeaders = {}) {
  let lastError;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
    try {
      const res = await fetch(url, {
        headers: { ...BASE_HEADERS, ...extraHeaders },
      });

      if (res.ok) {
        return await res.json();
      }

      const body = await res.text().catch(() => "");
      lastError = new Error(
        `Parks Canada API request failed: ${res.status} ${res.statusText} for ${url}` +
          (body ? ` — ${body.slice(0, 500)}` : ""),
      );
    } catch (err) {
      lastError = err;
    }

    if (attempt < MAX_RETRIES) {
      const backoffMs =
        Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS) + Math.random() * 250;
      await sleep(backoffMs);
    }
  }

  throw lastError;
}

function assertRequired(value, name) {
  if (value === undefined || value === null || value === "") {
    throw new Error(`parksCanadaClient: missing required param "${name}"`);
  }
}

/**
 * The Referer Parks Canada's front end would send for this search — sent
 * as a header (not navigated to), but still required to avoid a 403.
 */
function buildReferer({ resourceLocationId, mapId, bookingCategoryId, startDate, endDate }) {
  const params = new URLSearchParams({
    resourceLocationId: String(resourceLocationId),
    mapId: String(mapId),
    bookingCategoryId: String(bookingCategoryId),
    startDate,
    endDate,
  });
  return `${RESULTS_PAGE_URL}?${params.toString()}`;
}

/**
 * GET /resourceLocation (no query params)
 *
 * Returns every Parks Canada resourceLocation nationwide in one call —
 * confirmed live to be a plain top-level array of 114 entries (NOT the
 * { value, Count } wrapper originally assumed — corrected after checking a
 * real response). Each entry has resourceLocationId, localizedValues[]
 * (cultureName/shortName/fullName/description per locale, plus more),
 * transactionLocationId, resourceCategoryIds[], rootMapId, ianaTimeZone.
 *
 * This is the catalog root — catalogSync calls this once, then filters
 * down before calling getResources per matched location. Not cached here;
 * the caller owns caching policy same as getResources.
 */
async function getResourceLocations() {
  const url = `${BASE_URL}/resourceLocation`;
  return requestWithRetry(url);
}

// Confirmed live: resourceLocation entries tag locale via `cultureName`
// (e.g. "en-CA"/"fr-CA"). Kept as a candidate list rather than hardcoding
// just that one key, since resource-level localizedValues (from
// getResources) haven't been confirmed to use the same field name — if
// they don't, whichever key they do use should be added here.
// further.
const LOCALE_KEY_CANDIDATES = ["locale", "culture", "cultureName", "languageCode", "language"];

/**
 * Parks Canada's locale-tagged arrays (localizedValues on both
 * resourceLocation and resource entries) are a list of { <localeKey>:
 * "en-CA", ...fields } objects rather than a locale-keyed map. Returns the
 * entry for `locale` (default en-CA), or undefined if none of the candidate
 * locale keys match anything in the array.
 */
function findLocalizedValue(localizedValues, locale = "en-CA") {
  if (!Array.isArray(localizedValues)) return undefined;
  return localizedValues.find((entry) =>
    LOCALE_KEY_CANDIDATES.some((key) => entry[key] === locale),
  );
}

/**
 * GET /resourcelocation/resources?resourceLocationId={id}
 *
 * Returns every site/campground under a park location, keyed by resourceId.
 * Each entry has localizedValues[].name (en-CA/fr-CA), feeScheduleId,
 * mapIds[], and resourceModel (2 = real bookable site, 3 = trailhead/
 * access-point metadata, 0 = grazing/horse zone).
 *
 * Barely changes — callers should cache this for ~7 days (catalogSync is
 * the intended caller/cache owner, not this client).
 */
async function getResources(resourceLocationId) {
  assertRequired(resourceLocationId, "resourceLocationId");
  const url = `${BASE_URL}/resourcelocation/resources?resourceLocationId=${encodeURIComponent(
    resourceLocationId,
  )}`;
  return requestWithRetry(url);
}

/**
 * GET /maps?resourceLocationId={id}
 *
 * Maps a resourceLocationId to its mapId(s) — the mapId is what
 * availability/map actually keys off of.
 */
async function getMaps(resourceLocationId) {
  assertRequired(resourceLocationId, "resourceLocationId");
  const url = `${BASE_URL}/maps?resourceLocationId=${encodeURIComponent(resourceLocationId)}`;
  return requestWithRetry(url);
}

/**
 * GET /availability/map — the polling target.
 *
 * cartUid/cartTransactionUid/bookingUid are confirmed NOT validated
 * server-side, so a fresh random UUID is generated per call instead of
 * maintaining any cart/session lifecycle.
 *
 * getDailyAvailability is hardcoded true — the whole point of this client
 * is per-night granularity; false collapses the range into one value and
 * would silently break every caller.
 *
 * Response shape: { mapId, resourceAvailabilities: { [resourceId]: [{
 * availability, remainingQuota }, ...one per night] }, mapLinkAvailabilities }.
 * availability: 0 = unavailable, 1 = available online, 3 = not bookable via
 * this API at all (different jurisdiction or phone/in-person only) — 3 is a
 * static property of the site, never a live transition.
 */
async function getAvailabilityMap({
  mapId,
  resourceLocationId,
  startDate,
  endDate,
  bookingCategoryId = DEFAULT_BOOKING_CATEGORY_ID,
  numEquipment = DEFAULT_NUM_EQUIPMENT,
  peopleCapacityCategoryCounts = DEFAULT_PEOPLE_CAPACITY_CATEGORY_COUNTS,
}) {
  assertRequired(mapId, "mapId");
  assertRequired(resourceLocationId, "resourceLocationId");
  assertRequired(startDate, "startDate");
  assertRequired(endDate, "endDate");

  const params = new URLSearchParams({
    mapId: String(mapId),
    bookingCategoryId: String(bookingCategoryId),
    startDate,
    endDate,
    getDailyAvailability: "true",
    isReserving: "true",
    filterData: "[]",
    peopleCapacityCategoryCounts: JSON.stringify(peopleCapacityCategoryCounts),
    numEquipment: String(numEquipment),
    seed: new Date().toISOString(),
    cartUid: crypto.randomUUID(),
    cartTransactionUid: crypto.randomUUID(),
    bookingUid: crypto.randomUUID(),
    groupHoldUid: "",
  });

  const url = `${BASE_URL}/availability/map?${params.toString()}`;
  const referer = buildReferer({
    resourceLocationId,
    mapId,
    bookingCategoryId,
    startDate,
    endDate,
  });

  return requestWithRetry(url, { Referer: referer });
}

module.exports = {
  getResourceLocations,
  findLocalizedValue,
  getResources,
  getMaps,
  getAvailabilityMap,
  // Exported under a clearer name for external use: this is the same URL
  // sent as the Referer header, and it's also a real, directly-navigable
  // reservation.pc.gc.ca results page — used by notifier.js to build
  // "book this now" links in alert emails.
  buildResultsUrl: buildReferer,
};
