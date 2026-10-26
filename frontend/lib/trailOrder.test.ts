import test from "node:test";
import assert from "node:assert/strict";
import { isTrailSort, parkName, sortTrails, trailTitles } from "./trailOrder.ts";

const trail = (
  id: string,
  name: string,
  terrain: "easy" | "moderate" | "difficult" | "extreme",
  nights: number | null,
  km: number | null = null,
) => ({ id, name, region: "Banff National Park, AB", terrain, typical_duration_nights: nights, distance_km: km });

// API order is most popular first.
const trails = [
  trail("a", "Sentinel Pass", "difficult", 0, 11.6),
  trail("b", "Berg Lake Trail", "moderate", 3, 42),
  trail("c", "johnston Canyon", "easy", 0, 5),
  trail("d", "Rockwall", "extreme", 4, null),
  trail("e", "Mystery Loop", "moderate", null, null),
];
const ids = (list: { id: string }[]) => list.map((t) => t.id).join("");

test("popular keeps the API order", () => {
  assert.equal(ids(sortTrails(trails, "popular")), "abcde");
});

test("name sorts A–Z ignoring case", () => {
  assert.equal(ids(sortTrails(trails, "name")), "bceda");
});

test("difficulty sorts both ways and keeps popularity order on ties", () => {
  assert.equal(ids(sortTrails(trails, "easiest")), "cbead");
  assert.equal(ids(sortTrails(trails, "hardest")), "dabec");
});

test("trip length uses nights, then distance, with unknowns last", () => {
  assert.equal(ids(sortTrails(trails, "shortest")), "cabde");
  assert.equal(ids(sortTrails(trails, "longest")), "dbace");
});

test("sorting doesn't change the input", () => {
  sortTrails(trails, "name");
  assert.equal(ids(trails), "abcde");
});

test("only known sort keys are accepted from the URL", () => {
  assert.equal(isTrailSort("name"), true);
  assert.equal(isTrailSort("toString"), false);
  assert.equal(isTrailSort(null), false);
});

test("park name drops the province code", () => {
  assert.equal(parkName("Jasper National Park, AB"), "Jasper National Park");
  assert.equal(parkName("North Vancouver"), "North Vancouver");
});

test("clashing trail names get their park; unique names don't", () => {
  const titles = trailTitles([
    { id: "1", name: "Skyline Trail", region: "Jasper National Park, AB" },
    { id: "2", name: "Skyline Trail", region: "Cape Breton Highlands National Park, NS" },
    { id: "3", name: "Grouse Grind", region: "North Vancouver, BC" },
  ]);
  assert.equal(titles.get("1"), "Skyline Trail (Jasper National Park)");
  assert.equal(titles.get("2"), "Skyline Trail (Cape Breton Highlands National Park)");
  assert.equal(titles.get("3"), "Grouse Grind");
});
