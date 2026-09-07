import test from "node:test";
import assert from "node:assert/strict";
import { generatePackingList, type PackingCategory, type TripInputs } from "./packingList.ts";

function baseInput(overrides: Partial<TripInputs> = {}): TripInputs {
  return {
    nights: 2,
    location: "Test Trail",
    season: "summer",
    terrain: "easy",
    groupSize: 2,
    shareGear: true,
    ...overrides,
  };
}

function findItem(categories: PackingCategory[], name: string) {
  for (const category of categories) {
    const item = category.items.find((i) => i.name === name);
    if (item) return item;
  }
  return undefined;
}

test("Water filter and Multi-tool respect the shareGear toggle like every other shareable item", () => {
  const shared = generatePackingList(baseInput({ shareGear: true, groupSize: 2 }));
  const individual = generatePackingList(baseInput({ shareGear: false, groupSize: 2 }));

  const sharedFilter = findItem(shared, "Water filter");
  const individualFilter = findItem(individual, "Water filter");
  assert.equal(sharedFilter?.shared, true);
  assert.equal(individualFilter?.shared, false);
  // "Carry our own" means each person packs their own copy, not a pooled one.
  assert.equal(individualFilter?.qty, 2);

  const sharedTool = findItem(shared, "Multi-tool / knife");
  const individualTool = findItem(individual, "Multi-tool / knife");
  assert.equal(sharedTool?.shared, true);
  assert.equal(individualTool?.shared, false);
  assert.equal(individualTool?.qty, 2);
});

test("solo trips never mark shareable items as shared, even with shareGear on", () => {
  const solo = generatePackingList(baseInput({ shareGear: true, groupSize: 1 }));
  assert.equal(findItem(solo, "Water filter")?.shared, false);
  assert.equal(findItem(solo, "Multi-tool / knife")?.shared, false);
});
