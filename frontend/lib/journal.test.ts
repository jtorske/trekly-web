import test from "node:test";
import assert from "node:assert/strict";
import { badgeGrid, buildJournal, computeMilestones, groupColour, groupTrails, halves, regionTitle, sectionIndex, slugify, summarizeJournal } from "./journal.ts";
import { badgeOutline, nameFontSize, profileSilhouette } from "./badge.ts";
import { photoInputProblem, photoSize } from "./journalPhoto.ts";
import type { HikeLog } from "./hikeLogsApi.ts";
import type { TrailListItem } from "./trailsApi.ts";

let next = 0;
function trail(overrides: Partial<TrailListItem> = {}): TrailListItem {
  next += 1;
  return {
    id: `t${next}`,
    name: `Trail ${next}`,
    region: "Banff National Park, AB",
    terrain: "moderate",
    country_code: "CA",
    province_code: "AB",
    typical_duration_nights: 0,
    route_type: null,
    distance_km: null,
    elevation_gain_m: null,
    popularity_rank: next,
    retired_at: null,
    ...overrides,
  };
}

const log = (t: TrailListItem, hiked_on = "2026-08-14"): HikeLog => ({
  trail: t, hiked_on, note: null, photo_path: null, logged_at: "", updated_at: "",
});

test("region titles drop the province suffix", () => {
  assert.equal(regionTitle("Banff National Park, AB"), "Banff National Park");
  assert.equal(regionTitle("Deep Cove, North Vancouver, BC"), "Deep Cove, North Vancouver");
  assert.equal(regionTitle("California"), "California");
});

test("big regions get their own spread; small ones gather by province, west to east", () => {
  const trails = [
    trail({ region: "Gros Morne National Park, NL", province_code: "NL" }),
    ...[1, 2, 3].map(() => trail()),
    trail({ region: "Canmore, AB" }),
    trail({ region: "Joffre Lakes Provincial Park, BC", province_code: "BC" }),
    trail({ region: "Ucluelet, BC", province_code: "BC" }),
  ];
  const groups = groupTrails(trails);
  assert.deepEqual(
    groups.map((g) => [g.title, g.trails.length]),
    [["British Columbia", 2], ["Banff National Park", 3], ["More of Alberta", 1], ["Newfoundland and Labrador", 1]],
  );
  assert.equal(groups[0].subtitle, "2 places");
  assert.equal(groups[1].subtitle, "Alberta");
});

test("group colours are stable and from the palette", () => {
  assert.equal(groupColour("region:Banff National Park, AB"), groupColour("region:Banff National Park, AB"));
  assert.match(groupColour("place:CA-BC"), /^#[0-9a-f]{6}$/);
});

test("the book is contents, one section per group, then milestones", () => {
  const trails = [...Array.from({ length: 13 }, () => trail()), trail({ region: "Whitehorse, YT", province_code: "YT" })];
  const journal = buildJournal(trails, []);
  assert.deepEqual(
    journal.sections.map((s) => [s.kind, s.slug]),
    [["contents", null], ["group", "yukon"], ["group", "banff-national-park"], ["milestones", "milestones"]],
  );
  assert.equal(sectionIndex(journal, "banff-national-park"), 2);
  assert.equal(sectionIndex(journal, "milestones"), 3);
  assert.equal(sectionIndex(journal, null), 0);
  assert.equal(sectionIndex(journal, "nowhere"), 0, "unknown sections fall back to the contents");
});

test("section slugs are URL-safe and unique", () => {
  assert.equal(slugify("Parc national de la Gaspésie"), "parc-national-de-la-gaspesie");
  assert.equal(slugify("More of Alberta"), "more-of-alberta");
  const journal = buildJournal([trail({ region: "Milestones, AB" }), trail({ region: "Milestones, AB" }), trail({ region: "Milestones, AB" })], []);
  assert.deepEqual(journal.sections.map((s) => s.slug), [null, "milestones-2", "milestones"]);
});

test("a spread splits its trails with the extra one on the left", () => {
  assert.deepEqual(halves([1, 2, 3, 4, 5]), [[1, 2, 3], [4, 5]]);
  assert.deepEqual(halves([1]), [[1], []]);
});

test("badge grids stay portrait and hold every badge", () => {
  for (const count of [1, 2, 3, 5, 6, 7, 10, 19]) {
    const { columns, rows } = badgeGrid(count);
    assert.ok(columns <= 3 && columns * rows >= count && columns * (rows - 1) < count, `${count}`);
  }
  assert.deepEqual(badgeGrid(10), { columns: 3, rows: 4 });
});

test("progress counts the live catalogue plus retired trails the user hiked", () => {
  const live = [trail(), trail(), trail()];
  const retired = trail({ region: "California", country_code: "US", province_code: "CA", retired_at: "2026-10-01T00:00:00Z", popularity_rank: null });
  const journal = buildJournal(live, [log(live[0]), log(retired)]);
  assert.equal(journal.total, 4);
  assert.equal(journal.hiked, 2);
  assert.ok(journal.groups.some((g) => g.title === "United States" && g.trails[0].id === retired.id));
  // A guest sees only the live catalogue.
  assert.equal(buildJournal(live, []).total, 3);
});

test("milestones: first hike, first overnight, 5 parks, 100 km", () => {
  assert.deepEqual(computeMilestones([]).map((m) => m.earned), [false, false, false, false]);
  const parks = ["A", "B", "C", "D", "E"].map((name) => trail({ region: `${name} Park, AB`, distance_km: 21 }));
  const earned = computeMilestones(parks.map((t) => log(t)));
  assert.deepEqual(earned.map((m) => m.earned), [true, false, true, true]);
  const overnight = computeMilestones([log(trail({ typical_duration_nights: 2 }))]);
  assert.equal(overnight[1].earned, true);
  const partial = computeMilestones([log(trail({ distance_km: 42.5 })), log(trail({ distance_km: null }))]);
  assert.equal(partial[3].earned, false);
  assert.equal(partial[3].progress, 0.425);
  assert.match(partial[3].detail, /42 \/ 100 km/);
  // One canonical goal (100 km), labelled in whole units.
  assert.equal(computeMilestones([log(trail({ distance_km: 42.5 }))], "imperial")[3].detail, "Hike 62 mi in total (26 / 62 mi)");
  assert.equal(computeMilestones([log(trail({ distance_km: 97 }))])[3].detail, "Hike 100 km in total (97 / 100 km)");
  // 99.9 km is 62.07 mi: not earned, so it must not read "62 / 62 mi".
  assert.equal(computeMilestones([log(trail({ distance_km: 99.9 }))], "imperial")[3].detail, "Hike 62 mi in total (61 / 62 mi)");
  assert.equal(computeMilestones([log(trail({ distance_km: 100 }))], "imperial")[3].detail, "Hike 62 mi in total (62 / 62 mi)");
  assert.match(partial[2].detail, /1 \/ 5/);
});

test("each difficulty has its own badge outline", () => {
  const outlines = (["easy", "moderate", "difficult", "extreme"] as const).map((t) => badgeOutline(t));
  assert.equal(new Set(outlines).size, 4);
  for (const d of outlines) assert.match(d, /^M.*Z$/);
});

test("long names shrink to fit the arc, short ones are capped", () => {
  assert.equal(nameFontSize("Iceline", 42), 9.5);
  const long = nameFontSize("Parc national des Hautes-Gorges-de-la-Rivière-Malbaie Loop", 42);
  assert.ok(long < 9.5 && long >= 5.5);
});

test("elevation profiles become a silhouette; missing data falls back", () => {
  assert.equal(profileSilhouette(null, [0, 0, 100, 40]), null);
  assert.equal(profileSilhouette([1200], [0, 0, 100, 40]), null);
  const d = profileSilhouette([1000, 1500, 1200], [10, 20, 100, 40]);
  assert.equal(d, "M10 60L10 60L60 26L110 46.4L110 60Z");
});

test("photos are scaled down, never up, and odd files are refused", () => {
  assert.deepEqual(photoSize(4000, 3000, 1400), { width: 1400, height: 1050 });
  assert.deepEqual(photoSize(800, 600, 1400), { width: 800, height: 600 });
  assert.equal(photoInputProblem({ type: "image/heic", size: 10 }), "Use a JPEG, PNG or WebP photo.");
  assert.match(photoInputProblem({ type: "image/jpeg", size: 30 * 1024 * 1024 }) ?? "", /25 MB/);
  assert.equal(photoInputProblem({ type: "image/png", size: 10 }), null);
});

test("switching units never changes which milestones are earned", () => {
  const histories = [
    [],
    [log(trail({ distance_km: 96.6 }))], // 60 mi: not yet 100 km
    [log(trail({ distance_km: 99.9 }))],
    [log(trail({ distance_km: 100 }))],
    [log(trail({ distance_km: 62.1 })), log(trail({ distance_km: 37.9, typical_duration_nights: 2 }))],
    [log(trail({ distance_km: 150 })), log(trail({ distance_km: null }))],
    ["A", "B", "C", "D", "E"].map((region) => log(trail({ region: `${region}, AB`, distance_km: 21 }))),
  ];
  for (const logs of histories) {
    const metric = computeMilestones(logs, "metric");
    const imperial = computeMilestones(logs, "imperial");
    assert.deepEqual(
      imperial.map((m) => [m.id, m.earned, m.progress]),
      metric.map((m) => [m.id, m.earned, m.progress]),
    );
  }
});

test("journal summary: counts, nights and region progress, most complete first", () => {
  const banff = [1, 2, 3, 4].map(() => trail({ region: "Banff National Park, AB" }));
  const jasper = [1, 2, 3].map(() => trail({ region: "Jasper National Park, AB", typical_duration_nights: 2 }));
  const catalogue = [...banff, ...jasper];
  const hikes = [log(banff[0], "2026-06-01"), log(jasper[0], "2026-07-01"), log(jasper[1], "2026-08-01")];
  const summary = summarizeJournal(catalogue, hikes);
  assert.equal(summary.hiked, 3);
  assert.equal(summary.total, 7);
  assert.equal(summary.places, 2);
  assert.equal(summary.overnights, 2);
  assert.equal(summary.nights, 4);
  assert.deepEqual(summary.regions.map((r) => `${r.title} ${r.hiked}/${r.total}`), ["Jasper National Park 2/3", "Banff National Park 1/4"]);
  // Newest first, coloured like the book.
  assert.deepEqual(summary.recent.map((r) => r.hike.trail.id), [jasper[1].id, jasper[0].id, banff[0].id]);
  const book = buildJournal(catalogue, hikes);
  assert.equal(summary.recent[2].colour, book.groups.find((g) => g.title === "Banff National Park")?.colour);
});

test("journal summary totals distance and elevation only when every hike has them", () => {
  const known = trail({ distance_km: 12.5, elevation_gain_m: 600 });
  const unknown = trail({ distance_km: null, elevation_gain_m: 300 });
  const full = summarizeJournal([known], [log(known)]);
  assert.equal(full.distanceKm, 12.5);
  assert.equal(full.elevationM, 600);
  const partial = summarizeJournal([known, unknown], [log(known), log(unknown)]);
  assert.equal(partial.distanceKm, null);
  assert.equal(partial.elevationM, 900);
  assert.equal(summarizeJournal([known], []).distanceKm, null);
});

test("journal summary keeps the given order when dates are hidden, and stops at six stamps", () => {
  const trails = Array.from({ length: 8 }, () => trail());
  const undated = trails.map((t) => ({ trail: t, hiked_on: null }));
  const summary = summarizeJournal(trails, undated);
  assert.deepEqual(summary.recent.map((r) => r.hike.trail.id), trails.slice(0, 6).map((t) => t.id));
  assert.ok(summary.recent.every((r) => r.hike.hiked_on === null));
});
