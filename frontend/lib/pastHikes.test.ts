import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { mergeTrails, orderForPicker, searchPicker } from "./pastHikes.ts";
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
