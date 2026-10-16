import test from "node:test";
import assert from "node:assert/strict";
import {
  OUTSIDE,
  UNDECIDED,
  bookedNightsLost,
  decodeItinerary,
  defaultItinerary,
  describeNight,
  encodeItinerary,
  groupSizeWarning,
  isPastPlan,
  listPhrase,
  nightsInARow,
  resizeItinerary,
  sleepableSites,
  splitPlans,
} from "./planDraft.ts";
import type { CampgroundAvailability } from "./availabilityApi.ts";
import type { PlanNight, TripPlan, TripPlanSummary } from "./plansApi.ts";
import type { TrailCampground } from "./trailsApi.ts";

function site(id: string, extra: Partial<TrailCampground> = {}): TrailCampground {
  return { site_id: id, kind: "zone", retired: false, name: id, site_code: null, stop_name: null, ...extra } as TrailCampground;
}

const camp = (siteId: string) => ({ choice: "campground" as const, siteId });

test("one stop per night in route order; extra nights start undecided", () => {
  const stops = [{ sites: [site("a")] }, { sites: [site("b")] }];
  assert.deepEqual(defaultItinerary(stops, 1), [camp("a")]);
  assert.deepEqual(defaultItinerary(stops, 3), [camp("a"), camp("b"), UNDECIDED]);
});

test("retired sites, empty stops and permits are skipped", () => {
  const stops = [
    { sites: [site("permit", { kind: "trail_permit" })] },
    { sites: [site("gone", { retired: true })] },
    { sites: [site("c")] },
  ];
  assert.deepEqual(defaultItinerary(stops, 2), [camp("c"), UNDECIDED]);
  assert.deepEqual(sleepableSites([site("p", { kind: "trail_permit" }), site("x")]).map((s) => s.site_id), ["x"]);
});

test("after a check, a pad that was free that night is preferred", () => {
  const stops = [{ sites: [site("ph1"), site("ph2")] }, { sites: [site("ph3"), site("ph4")] }];
  const found = (id: string, statuses: string[]): [string, CampgroundAvailability] => [
    id,
    { site_id: id, summary: "partial", nights: statuses.map((status, i) => ({ date: `2026-10-2${i}`, status })) } as CampgroundAvailability,
  ];
  const availability = new Map([
    found("ph1", ["full", "available"]),
    found("ph2", ["available", "full"]),
    found("ph3", ["available", "full"]),
    found("ph4", ["available", "full"]),
  ]);
  // Night 1 at stop 1: ph1 is full, ph2 free. Night 2 at stop 2: both full, so the first pad.
  assert.deepEqual(defaultItinerary(stops, 2, availability), [camp("ph2"), camp("ph3")]);
});

test("resizing keeps earlier nights", () => {
  const itinerary = [camp("a"), OUTSIDE, camp("c")];
  assert.deepEqual(resizeItinerary(itinerary, 2), [camp("a"), OUTSIDE]);
  assert.deepEqual(resizeItinerary(itinerary, 4), [...itinerary, UNDECIDED]);
});

function night(index: number, extra: Partial<PlanNight> = {}): PlanNight {
  return {
    night_index: index,
    date: `2026-10-2${index}`,
    choice: "campground",
    site: { id: `s${index}`, name: `Camp ${index}`, site_code: null, stop_name: null } as PlanNight["site"],
    booked_by_me: false,
    status: "not_checked",
    alert_id: null,
    last_status: null,
    last_checked_at: null,
    ...extra,
  };
}

test("booked nights an edit would unmark: dropped, moved or a different campground", () => {
  const plan = {
    start_date: "2026-10-20",
    itinerary: [night(0, { booked_by_me: true }), night(1), night(2, { booked_by_me: true })],
  } as TripPlan;
  const same = [camp("s0"), camp("s1"), camp("s2")];
  assert.deepEqual(bookedNightsLost(plan, "2026-10-20", same), []);
  // Shortening only loses the dropped booked night; an unbooked change is fine.
  assert.deepEqual(bookedNightsLost(plan, "2026-10-20", [camp("s0"), UNDECIDED]).map((n) => n.night_index), [2]);
  assert.deepEqual(bookedNightsLost(plan, "2026-10-21", same).map((n) => n.night_index), [0, 2]);
  assert.deepEqual(bookedNightsLost(plan, "2026-10-20", [OUTSIDE, camp("s1"), camp("s2")]).map((n) => n.night_index), [0]);
});

test("describing a night names its date and campground", () => {
  assert.equal(describeNight(night(2), (iso) => `<${iso}>`), "night 3 (<2026-10-22>) at Camp 2");
  assert.equal(describeNight(night(0, { choice: "outside", site: null }), (iso) => iso), "night 1 (2026-10-20) outside Parks Canada");
  assert.equal(listPhrase(["a"]), "a");
  assert.equal(listPhrase(["a", "b", "c"]), "a, b and c");
});

test("a guest's itinerary survives the sign-in round trip", () => {
  const itinerary = [camp("site-1"), OUTSIDE, UNDECIDED];
  const code = encodeItinerary(itinerary);
  assert.equal(code, "site-1.o.u");
  assert.deepEqual(decodeItinerary(code, 3, new Set(["site-1"])), itinerary);
  // Unknown sites become undecided, and the length follows the stay.
  assert.deepEqual(decodeItinerary("nope.o", 3, new Set()), [UNDECIDED, OUTSIDE, UNDECIDED]);
  assert.equal(decodeItinerary(null, 2, new Set()), null);
});

test("group size warning only when the party is too big", () => {
  assert.equal(groupSizeWarning(4, 4), null);
  assert.equal(groupSizeWarning(6, null), null);
  assert.match(groupSizeWarning(6, 4) ?? "", /limited to 4 people; your party is 6/);
});

test("a plan turns past the day after its last night, by the user's own date", () => {
  const plan = { last_night: "2026-10-22" };
  assert.equal(isPastPlan(plan, "2026-10-22"), false);
  assert.equal(isPastPlan(plan, "2026-10-23"), true);

  const p = (id: string, start: string, last: string) => ({ id, start_date: start, last_night: last }) as TripPlanSummary;
  const { upcoming, past } = splitPlans(
    [p("old", "2026-09-01", "2026-09-02"), p("soon", "2026-10-25", "2026-10-26"), p("now", "2026-10-21", "2026-10-23"), p("older", "2026-08-01", "2026-08-03")],
    "2026-10-23",
  );
  assert.deepEqual(upcoming.map((x) => x.id), ["now", "soon"]);
  assert.deepEqual(past.map((x) => x.id), ["old", "older"]);
});

test("a Book link covers the nights in a row at that campground", () => {
  const at = (id: string | null) => ({ site: id ? ({ id } as PlanNight["site"]) : null });
  const itinerary = [at("a"), at("a"), at("b"), at(null), at("a")];
  assert.equal(nightsInARow(itinerary, 0), 2);
  assert.equal(nightsInARow(itinerary, 1), 1);
  assert.equal(nightsInARow(itinerary, 2), 1);
  assert.equal(nightsInARow(itinerary, 3), 1);
  assert.equal(nightsInARow(itinerary, 4), 1);
});
