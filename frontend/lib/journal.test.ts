import test from "node:test";
import assert from "node:assert/strict";
import { BADGES_PER_PAGE, buildJournal, computeMilestones, groupColour, groupTrails, regionTitle, spreadCount, spreadOfPage, spreadPages } from "./journal.ts";
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

test("each group starts on a left-hand page and fills whole spreads", () => {
  const trails = [...Array.from({ length: 13 }, () => trail()), trail({ region: "Whitehorse, YT", province_code: "YT" })];
  const journal = buildJournal(trails, []);
  assert.equal(journal.pages[0].kind, "cover");
  const contents = journal.pages.slice(1, 3).flatMap((p) => (p.kind === "contents" ? p.groups : []));
  assert.equal(contents.length, journal.groups.length, "the contents span the first spread");
  assert.equal(journal.pages.at(-1)?.kind, "back");
  assert.equal(journal.pages.at(-2)?.kind, "milestones");
  for (const start of journal.groupStart.values()) assert.equal(start % 2, 1, "left pages are odd");
  const banff = journal.pages.filter((p) => p.kind === "group" && p.group.title === "Banff National Park");
  // 13 trails = 3 pages of 6, padded to 4 so the next group starts on a left page.
  assert.equal(banff.length, 4);
  assert.ok(banff.every((p) => p.kind === "group" && p.trails.length <= BADGES_PER_PAGE));
  assert.equal(journal.pages.length % 2, 1, "cover + whole spreads + milestones/back");
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
  assert.match(partial[2].detail, /1 \/ 5/);
});

test("desktop spreads pair pages around the cover", () => {
  assert.deepEqual(spreadPages(0), [-1, 0]);
  assert.deepEqual(spreadPages(2), [3, 4]);
  assert.equal(spreadOfPage(0), 0);
  assert.equal(spreadOfPage(3), 2);
  assert.equal(spreadOfPage(4), 2);
  assert.equal(spreadCount(7), 4);
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
