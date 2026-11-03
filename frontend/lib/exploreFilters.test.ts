import test from "node:test";
import assert from "node:assert/strict";
import {
  EMPTY_FILTERS,
  activeFilterCount,
  clearFilters,
  exploreHref,
  exploreSearch,
  formatMapView,
  keepViewParams,
  parseExploreParams,
  parseExploreView,
  parseFollowMap,
  parseMapView,
  provinceOrder,
  searchAreaFor,
  toggle,
  toggleTrip,
  withProvinces,
  withViewParam,
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

test("the list searches the map's visible area, or everywhere once it takes in all of Canada", () => {
  assert.deepEqual(searchAreaFor({ west: -117.123456, south: 50.5, east: -114, north: 52.25 }), {
    west: -117.1235,
    south: 50.5,
    east: -114,
    north: 52.25,
  });
  // All of Canada, or the whole world: no area at all.
  assert.equal(searchAreaFor({ west: -142, south: 41, east: -52, north: 71 }), undefined);
  assert.equal(searchAreaFor({ west: -400, south: -85, east: 400, north: 85 }), undefined);
  // Most of Canada but not the east coast is still an area.
  assert.ok(searchAreaFor({ west: -142, south: 41, east: -70, north: 71 }));
  // A repeated world's longitudes come back into range; west past east crosses the antimeridian.
  assert.deepEqual(searchAreaFor({ west: 170, south: -10, east: 190, north: 10 }), {
    west: 170,
    south: -10,
    east: -170,
    north: 10,
  });
  assert.equal(searchAreaFor({ west: 100, south: 0, east: 180, north: 10 })?.east, 180);
  assert.equal(searchAreaFor({ west: -480, south: 50, east: -470, north: 52 })?.west, -120);
});

test("an old shared link's map area is ignored", () => {
  assert.deepEqual(parse("q=lake&area=-117,50,-114,52"), { ...parse("q=lake") });
  assert.equal(exploreSearch(parse("q=lake&area=-117,50,-114,52")), "q=lake");
});

test("the map position and Map/List choice are view state that survives filter changes", () => {
  assert.deepEqual(parseMapView(new URLSearchParams("map=51.1784,-115.5708,9.5")), {
    lat: 51.1784,
    lng: -115.5708,
    zoom: 9.5,
  });
  assert.equal(formatMapView({ lat: 51.178412, lng: -115.570812, zoom: 9.4567 }), "51.1784,-115.5708,9.46");
  for (const bad of ["", "map=1,2", "map=91,0,5", "map=0,0,30", "map=x,0,5"]) {
    assert.equal(parseMapView(new URLSearchParams(bad)), null, bad);
  }
  assert.equal(parseExploreView(new URLSearchParams("view=map")), "map");
  assert.equal(parseExploreView(new URLSearchParams("view=nope")), "list");

  const current = new URLSearchParams("trip=day&map=51,-115,9&view=map");
  assert.equal(keepViewParams("trip=overnight", current), "trip=overnight&map=51%2C-115%2C9&view=map");
  assert.equal(keepViewParams("", new URLSearchParams("trip=day")), "");
  assert.equal(withViewParam(current, "view", null), "trip=day&map=51%2C-115%2C9");
  assert.equal(withViewParam(new URLSearchParams("trip=day"), "map", "1,2,3"), "trip=day&map=1%2C2%2C3");
});

test("Search as I move the map is on unless the URL turns it off, and survives filter changes", () => {
  assert.equal(parseFollowMap(new URLSearchParams("")), true);
  assert.equal(parseFollowMap(new URLSearchParams("follow=0")), false);
  assert.equal(parseFollowMap(new URLSearchParams("follow=1")), true);
  assert.equal(keepViewParams("trip=day", new URLSearchParams("q=x&follow=0")), "trip=day&follow=0");
});

test("the trip quick chips swap and clear the trip type", () => {
  assert.equal(toggleTrip(EMPTY_FILTERS, "day").trip, "day");
  assert.equal(toggleTrip({ ...EMPTY_FILTERS, trip: "day" }, "overnight").trip, "overnight");
  assert.equal(toggleTrip({ ...EMPTY_FILTERS, trip: "day" }, "day").trip, undefined);
});
