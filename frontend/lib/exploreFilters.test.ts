import test from "node:test";
import assert from "node:assert/strict";
import {
  EMPTY_FILTERS,
  activeFilterCount,
  clearFilters,
  exploreHref,
  exploreSearch,
  parseExploreParams,
  provinceOrder,
  toggle,
  withProvinces,
  withinKm,
  withoutNear,
  type ExploreFilters,
} from "./exploreFilters.ts";

const parse = (search: string) => parseExploreParams(new URLSearchParams(search));

test("an empty URL is no filters", () => {
  assert.deepEqual(parse(""), { ...EMPTY_FILTERS, trip: undefined, terrain: undefined, within: undefined });
  assert.equal(exploreSearch(EMPTY_FILTERS), "");
  assert.equal(exploreHref({}), "/trail-list");
});

test("every filter round-trips through the URL", () => {
  const filters: ExploreFilters = {
    q: "lake",
    trip: "day",
    terrain: "easy",
    provinces: ["AB", "BC"],
    parkTypes: ["national", "other"],
    parks: ["Banff National Park", "Parc national de la Gaspésie"],
    near: true,
    within: { value: 50, unit: "km" },
    sort: "nearest",
  };
  const search = exploreSearch(filters);
  assert.equal(
    search,
    "q=lake&trip=day&terrain=easy&province=AB&province=BC&park_type=national&park_type=other" +
      "&park=Banff+National+Park&park=Parc+national+de+la+Gasp%C3%A9sie&near=1&within=50km&sort=nearest",
  );
  assert.deepEqual(parse(search), filters);
});

test("the URL never carries a position, only that location is on", () => {
  const search = exploreSearch({ ...EMPTY_FILTERS, near: true, within: { value: 25, unit: "mi" } });
  assert.equal(search, "near=1&within=25mi");
  assert.doesNotMatch(search, /lat|lng|\d+\.\d+/);
});

test("bad or repeated values are dropped", () => {
  const filters = parse(
    "trip=weekend&terrain=brutal&province=ab&province=AB&province=Alberta&park_type=regional&park_type=national" +
      "&park_type=national&park=&park=%20Banff%20National%20Park%20&within=30km&sort=sideways",
  );
  assert.equal(filters.trip, undefined);
  assert.equal(filters.terrain, undefined);
  assert.deepEqual(filters.provinces, ["AB"]);
  assert.deepEqual(filters.parkTypes, ["national"]);
  assert.deepEqual(filters.parks, ["Banff National Park"]);
  // A distance only counts with near=1, and only from the offered options.
  assert.equal(filters.within, undefined);
  assert.equal(parse("near=1&within=30km").within, undefined);
  assert.deepEqual(parse("near=1&within=250mi").within, { value: 250, unit: "mi" });
  assert.equal(filters.sort, "popular");
});

test("Nearest needs location on", () => {
  assert.equal(parse("sort=nearest").sort, "popular");
  assert.equal(parse("near=1&sort=nearest").sort, "nearest");
  assert.equal(exploreSearch({ ...EMPTY_FILTERS, sort: "nearest" }), "");
  assert.equal(exploreSearch({ ...EMPTY_FILTERS, sort: "name" }), "sort=name");
});

test("turning location off drops the distance and the Nearest sort", () => {
  const on = parse("near=1&within=100km&sort=nearest&province=AB");
  assert.equal(exploreSearch(withoutNear(on)), "province=AB");
  assert.equal(withoutNear({ ...on, sort: "name" }).sort, "name");
});

test("the filter count leaves out the search box and sort", () => {
  assert.equal(activeFilterCount(parse("q=lake&sort=name")), 0);
  assert.equal(
    activeFilterCount(parse("trip=day&terrain=easy&province=AB&province=BC&park_type=national&park=X&near=1")),
    7,
  );
});

test("Clear all keeps the search and drops every filter", () => {
  const cleared = clearFilters(parse("q=lake&trip=day&province=AB&park=Banff+National+Park&near=1&sort=nearest"));
  assert.equal(exploreSearch(cleared), "q=lake");
  assert.equal(clearFilters(parse("province=AB&sort=name")).sort, "name");
});

test("a park link filters to just that park", () => {
  assert.equal(exploreHref({ parks: ["Kananaskis Country"] }), "/trail-list?park=Kananaskis+Country");
  assert.deepEqual(parse("park=Kananaskis+Country").parks, ["Kananaskis Country"]);
});

test("unpicking a province drops parks outside the remaining ones", () => {
  const parkProvinces = new Map([
    ["Banff National Park", ["AB"]],
    ["Yoho National Park", ["BC"]],
  ]);
  const filters = parse("province=AB&province=BC&park=Banff+National+Park&park=Yoho+National+Park&park=Unknown");
  const next = withProvinces(filters, ["AB"], parkProvinces);
  assert.deepEqual(next.provinces, ["AB"]);
  // Parks the counts don't know yet are kept rather than guessed at.
  assert.deepEqual(next.parks, ["Banff National Park", "Unknown"]);
  // With no province picked, nothing narrows the parks.
  assert.deepEqual(withProvinces(filters, [], parkProvinces).parks, filters.parks);
});

test("toggle adds and removes", () => {
  assert.deepEqual(toggle(["AB"], "BC"), ["AB", "BC"]);
  assert.deepEqual(toggle(["AB", "BC"], "AB"), ["BC"]);
});

test("provinces sort west to east, then the territories", () => {
  assert.deepEqual(["YT", "NL", "AB", "BC", "ON", "ZZ"].sort(provinceOrder), ["BC", "AB", "ON", "NL", "YT", "ZZ"]);
});

test("distances in miles become km for the API", () => {
  assert.equal(withinKm({ value: 50, unit: "km" }), 50);
  assert.ok(Math.abs(withinKm({ value: 25, unit: "mi" }) - 40.2336) < 1e-9);
});
