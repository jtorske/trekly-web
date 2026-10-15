import test from "node:test";
import assert from "node:assert/strict";
import { bookingLabel, campgroundView, capacityFacts, groupStops, kindLabel } from "./campgrounds.ts";
import type { TrailBooking, TrailCampground, TrailCampgrounds } from "../../lib/trailsApi.ts";

function site(overrides: Partial<TrailCampground> = {}): TrailCampground {
  return {
    site_id: overrides.name ?? "x",
    route_order: 1,
    stop_name: null,
    notes: null,
    confidence: "exact",
    retired: false,
    name: "Evelyn Creek",
    site_code: "27",
    kind: "zone",
    area: "Skyline",
    park: { name: "Jasper", province_code: "AB" },
    reservable_capacity: 4,
    max_capacity: 6,
    max_group_size: null,
    provider: "parks_canada",
    ...overrides,
  };
}

const PARKS_CANADA: TrailBooking = {
  system: "parks_canada",
  name: "Parks Canada",
  url: "https://reservation.pc.gc.ca",
  covers: "all",
  confirmed: true,
  note: null,
};

function data(overrides: Partial<TrailCampgrounds> = {}): TrailCampgrounds {
  return {
    trail_id: "t",
    trip_type: "overnight",
    overnight_option: false,
    route_order_approximate: false,
    booking: [PARKS_CANADA],
    booking_links: [],
    campgrounds: [site()],
    ...overrides,
  };
}

test("pads sharing a stop and route position become one stop", () => {
  const stops = groupStops([
    site({ name: "HF1", stop_name: "Hook Falls", route_order: 1 }),
    site({ name: "HF2", stop_name: "Hook Falls", route_order: 1, retired: true }),
    site({ name: "WR1", stop_name: "Willow River", route_order: 2 }),
    site({ name: "Signal", route_order: 3 }),
    site({ name: "Tekarra", route_order: 3 }),
  ]);
  assert.deepEqual(
    stops.map((s) => [s.label, s.sites.map((x) => x.name), s.retired]),
    [
      ["Hook Falls", ["HF1", "HF2"], false],
      ["Willow River", ["WR1"], false],
      ["Signal", ["Signal"], false],
      ["Tekarra", ["Tekarra"], false],
    ],
  );
});

test("a stop is retired only when every pad is", () => {
  const [stop] = groupStops([
    site({ name: "A", stop_name: "Cove", retired: true }),
    site({ name: "B", stop_name: "Cove", retired: true }),
  ]);
  assert.equal(stop.retired, true);
});

test("kind labels and capacity copy", () => {
  assert.equal(kindLabel("zone"), "Campground");
  assert.equal(kindLabel("site", 3), "3 campsites");
  assert.equal(kindLabel("trail_permit"), "Trail permit");
  assert.deepEqual(capacityFacts(site()), ["Quota 4 a night", "Groups up to 6"]);
  assert.deepEqual(capacityFacts(site({ kind: "trail_permit", reservable_capacity: 25, max_capacity: null })), [
    "Quota 25 a day",
  ]);
  assert.deepEqual(capacityFacts(site({ reservable_capacity: null, max_capacity: null })), []);
});

test("booking labels name only confirmed systems", () => {
  assert.equal(bookingLabel({ ...PARKS_CANADA, system: "bc_parks", name: "BC Parks" }), "Booked through BC Parks");
  assert.equal(bookingLabel({ ...PARKS_CANADA, system: "yukon_parks", name: null, confirmed: false }), "Booked outside Trekly");
  assert.equal(
    bookingLabel({ ...PARKS_CANADA, system: "none", name: "No reservations (first come, first served)" }),
    "No reservations (first come, first served)",
  );
});

test("overnight trail with Parks Canada campgrounds", () => {
  const view = campgroundView(data());
  assert.equal(view.visible, true);
  assert.equal(view.parksCanada, PARKS_CANADA);
  assert.deepEqual(view.elsewhere, []);
});

test("overnight trail booked elsewhere shows only the note", () => {
  const bc = { ...PARKS_CANADA, system: "bc_parks", name: "BC Parks", url: null };
  const view = campgroundView(data({ campgrounds: [], booking: [bc] }));
  assert.equal(view.visible, true);
  assert.equal(view.parksCanada, null);
  assert.deepEqual(view.elsewhere, [bc]);
});

test("Parks Canada with no listed sites is a note, not a list", () => {
  const view = campgroundView(data({ campgrounds: [], booking: [{ ...PARKS_CANADA, confirmed: false, name: null }] }));
  assert.equal(view.parksCanada, null);
  assert.equal(view.elsewhere.length, 1);
});

test("day hikes show campgrounds only as an overnight option", () => {
  assert.equal(campgroundView(data({ trip_type: "day" })).visible, false);
  assert.equal(campgroundView(data({ trip_type: "day", overnight_option: true })).visible, true);
  assert.equal(campgroundView(data({ trip_type: "day", campgrounds: [], booking: [] })).visible, false);
  assert.equal(campgroundView(null).visible, false);
});
