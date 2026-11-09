import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  distanceKm,
  filterProvinces,
  groupForPicker,
  groupHeading,
  hasSharedName,
  mergeTrails,
  orderForPicker,
  pickedCount,
  pickerProvinces,
  placeLine,
  searchPicker,
  sharedNames,
  sortForPicker,
} from "./pastHikes.ts";
import type { TrailListItem } from "./trailsApi.ts";

const trail = (id: string, more: Partial<TrailListItem> = {}): TrailListItem =>
  ({
    id,
    name: `Trail ${id}`,
    region: "Banff National Park, AB",
    terrain: "moderate",
    country_code: "CA",
    province_code: "AB",
    park_name: "Banff National Park",
    park_type: "national",
    typical_duration_nights: 0,
    route_type: null,
    distance_km: null,
    elevation_gain_m: null,
    popularity_rank: Number(id),
    retired_at: null,
    ...more,
  }) as TrailListItem;

describe("orderForPicker", () => {
  const trails = [
    trail("1"),
    trail("2", { province_code: "BC", region: "Garibaldi Provincial Park, BC", park_name: "Garibaldi Provincial Park" }),
    trail("3", { province_code: "NS", region: "Cape Breton Highlands, NS", park_name: "Cape Breton Highlands National Park" }),
    trail("4", { province_code: "BC", region: "Strathcona, BC", park_name: "Strathcona Provincial Park" }),
    trail("5", { retired_at: "2026-10-01T00:00:00Z" }),
  ];

  it("is popularity order with no preferences, without retired trails", () => {
    assert.deepEqual(orderForPicker(trails).map((t) => t.id), ["1", "2", "3", "4"]);
  });

  it("puts the home province first, then favourite regions, then the rest", () => {
    const ordered = orderForPicker(trails, { homeProvince: "BC", favouriteRegions: ["Cape Breton"] });
    assert.deepEqual(ordered.map((t) => t.id), ["2", "4", "3", "1"]);
  });

  it("matches favourite regions ignoring case and accents", () => {
    assert.equal(orderForPicker(trails, { favouriteRegions: ["strathcôna"] })[0].id, "4");
  });
});

describe("searchPicker", () => {
  const trails = [trail("1", { name: "Lake Agnes Teahouse" }), trail("2", { name: "Berg Lake", park_name: "Mount Robson" })];

  it("needs every word in the name, park or region", () => {
    assert.deepEqual(searchPicker(trails, "lake agnes").map((t) => t.id), ["1"]);
    assert.deepEqual(searchPicker(trails, "robson lake").map((t) => t.id), ["2"]);
    assert.equal(searchPicker(trails, "  ").length, 2);
  });
});

describe("mergeTrails", () => {
  it("adds only new, active server results after the local ones", () => {
    const merged = mergeTrails([trail("1")], [trail("1"), trail("9"), trail("8", { retired_at: "2026-01-01" })]);
    assert.deepEqual(merged.map((t) => t.id), ["1", "9"]);
  });
});

// A small catalogue across three provinces.
const BANFF = { province_code: "AB", park_name: "Banff National Park", region: "Banff National Park, AB" };
const JASPER = { province_code: "AB", park_name: "Jasper National Park", region: "Jasper National Park, AB" };
const YOHO = { province_code: "BC", park_name: "Yoho National Park", region: "Yoho National Park, BC" };
const GARIBALDI = { province_code: "BC", park_name: "Garibaldi Provincial Park", region: "Garibaldi, BC" };
const GROS_MORNE = { province_code: "NL", park_name: "Gros Morne National Park", region: "Gros Morne, NL" };
const NAMES: Record<string, string> = { AB: "Alberta", BC: "British Columbia", NL: "Newfoundland and Labrador" };
const catalogue = [
  trail("1", { ...BANFF, name: "Lake Agnes", latitude: 51.42, longitude: -116.22 }),
  trail("2", { ...YOHO, name: "Iceline", latitude: 51.5, longitude: -116.5 }),
  trail("3", { ...BANFF, name: "Sentinel Pass", latitude: 51.32, longitude: -116.18 }),
  trail("4", { ...JASPER, name: "Skyline Trail", latitude: 52.8, longitude: -117.9 }),
  trail("5", { ...GROS_MORNE, name: "Gros Morne Mountain", latitude: 49.57, longitude: -57.8 }),
  trail("6", { ...GARIBALDI, name: "Panorama Ridge", latitude: 49.94, longitude: -122.98 }),
  trail("7", { ...GROS_MORNE, name: "Skyline Trail", latitude: 49.6, longitude: -57.9 }),
  trail("8", { ...BANFF, name: "Old Trail", retired_at: "2026-01-01T00:00:00Z" }),
  trail("9", { ...BANFF, name: "Unmapped", latitude: null, longitude: null, popularity_rank: 2.5 }),
];
const titles = (groups: { title: string }[]) => groups.map((g) => g.title);

describe("groupForPicker", () => {
  it("puts home province parks first, then radar parks, then the rest by province", () => {
    const groups = groupForPicker(catalogue, { homeProvince: "BC", favouriteRegions: ["Gros Morne National Park"] }, (c) => NAMES[c]);
    assert.deepEqual(titles(groups), [
      // Home (BC), by each park's most popular trail.
      "Yoho National Park",
      "Garibaldi Provincial Park",
      // On their radar.
      "Gros Morne National Park",
      // Everything else: by province, then park, A–Z.
      "Banff National Park",
      "Jasper National Park",
    ]);
  });

  it("counts each park's live trails, most popular first", () => {
    const banff = groupForPicker(catalogue).find((g) => g.title === "Banff National Park")!;
    assert.deepEqual(banff.trails.map((t) => t.name), ["Lake Agnes", "Unmapped", "Sentinel Pass"]);
    assert.equal(groupHeading(banff), "Banff National Park · 3 trails");
    assert.equal(groupHeading({ ...banff, trails: banff.trails.slice(0, 1) }), "Banff National Park · 1 trail");
  });

  it("with no answers, groups go by province then park", () => {
    assert.deepEqual(titles(groupForPicker(catalogue, {}, (c) => NAMES[c])), [
      "Banff National Park",
      "Jasper National Park",
      "Garibaldi Provincial Park",
      "Yoho National Park",
      "Gros Morne National Park",
    ]);
  });
});

describe("sortForPicker", () => {
  const names = (trails: TrailListItem[]) => trails.map((t) => t.name);

  it("most popular, and A–Z with same names told apart by park", () => {
    assert.deepEqual(names(sortForPicker(catalogue, "popular")), [
      "Lake Agnes", "Iceline", "Unmapped", "Sentinel Pass", "Skyline Trail", "Gros Morne Mountain", "Panorama Ridge", "Skyline Trail",
    ]);
    const az = sortForPicker(catalogue, "az");
    assert.deepEqual(names(az).slice(0, 3), ["Gros Morne Mountain", "Iceline", "Lake Agnes"]);
    assert.deepEqual(az.filter((t) => t.name === "Skyline Trail").map((t) => t.park_name), ["Gros Morne National Park", "Jasper National Park"]);
  });

  it("nearest to me, trails without a trailhead last; no location falls back to popular", () => {
    const whistler = { lat: 50.12, lon: -122.95 };
    const near = sortForPicker(catalogue, "nearest", whistler);
    assert.equal(near[0].name, "Panorama Ridge");
    assert.equal(near.at(-1)?.name, "Unmapped");
    assert.deepEqual(names(sortForPicker(catalogue, "nearest", null)), names(sortForPicker(catalogue, "popular")));
  });

  it("never lists retired trails", () => {
    for (const sort of ["popular", "az", "nearest"] as const) {
      assert.ok(!sortForPicker(catalogue, sort, { lat: 51, lon: -116 }).some((t) => t.name === "Old Trail"));
    }
  });

  it("measures distance on the globe", () => {
    // Banff to Vancouver is about 575 km as the crow flies.
    const km = distanceKm({ lat: 51.18, lon: -115.57 }, { lat: 49.28, lon: -123.12 });
    assert.ok(km > 560 && km < 590, String(km));
    assert.equal(distanceKm({ lat: 50, lon: -120 }, { lat: 50, lon: -120 }), 0);
  });
});

describe("province chips", () => {
  it("offers the provinces with trails, most first, and filters to the chosen ones", () => {
    assert.deepEqual(pickerProvinces(catalogue), ["AB", "BC", "NL"]);
    assert.equal(filterProvinces(catalogue, new Set()).length, catalogue.length);
    assert.deepEqual(new Set(filterProvinces(catalogue, new Set(["NL", "BC"])).map((t) => t.province_code)), new Set(["NL", "BC"]));
  });
});

describe("same-name trails", () => {
  it("always show where they are", () => {
    const shared = sharedNames(catalogue);
    assert.ok(hasSharedName(catalogue[3], shared) && !hasSharedName(catalogue[0], shared));
    const [jasper, grosMorne] = [catalogue[3], catalogue[6]];
    assert.equal(placeLine(jasper, shared, catalogue), "Jasper National Park");
    assert.equal(placeLine(grosMorne, shared, catalogue), "Gros Morne National Park");
    // Same name and same park name: the province tells them apart.
    const twins = [trail("a", { name: "Ridge Loop", park_name: null, region: "Crown land", province_code: "BC" }),
      trail("b", { name: "Ridge Loop", park_name: null, region: "Crown land", province_code: "ON" })];
    assert.equal(placeLine(twins[0], sharedNames(twins), twins), "Crown land, BC");
  });
});

describe("the picked counter", () => {
  it("reads naturally", () => {
    assert.equal(pickedCount(0), "Nothing picked yet");
    assert.equal(pickedCount(1), "1 trail picked");
    assert.equal(pickedCount(6), "6 trails picked");
  });
});
