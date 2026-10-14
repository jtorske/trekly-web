import test from "node:test";
import assert from "node:assert/strict";
import { ALL_SLOTS, CORE_SLOTS, MORE_ZONES, ZONES, groupItemsBySlot, slotForCategory, zoneCoverage } from "./slots.ts";
import type { GearItem } from "../../lib/gearApi.ts";

// Mirrors backend/app/catalog/taxonomy.py — every subcategory must have a slot.
const TAXONOMY: Record<string, string[]> = {
  backpack: ["backpacks", "pack-accessories"],
  shelter: ["tents", "tarps", "footprints", "bivy-sacks", "stakes-guylines"],
  sleep: ["sleeping-bags", "quilts", "sleeping-pads", "pillows", "sleep-liners"],
  clothing: ["rainwear", "insulation", "fleece-midlayers", "base-layers", "wind-layers", "headwear-gloves"],
  cooking: ["stoves", "cookware", "fuel-accessories", "utensils", "food-storage"],
  hydration: ["water-treatment", "bottles-reservoirs"],
  footwear: ["hiking-boots", "trail-runners", "gaiters", "camp-shoes"],
  navigation: ["gps-satellite", "compasses", "watches"],
  safety: ["first-aid", "emergency", "bear-safety"],
  accessories: ["lighting", "trekking-poles", "storage", "repair", "power", "misc"],
};

test("every catalogue subcategory maps to exactly one slot in its own zone", () => {
  const seen = new Map<string, string>();
  for (const slot of ALL_SLOTS) {
    for (const category of slot.categories) {
      assert.ok(!seen.has(category), `${category} is in two slots`);
      seen.set(category, slot.key);
    }
  }
  for (const [top, subs] of Object.entries(TAXONOMY)) {
    for (const sub of subs) {
      const slot = slotForCategory(sub);
      assert.equal(slot.zone, top, `${sub} should live in the ${top} zone`);
    }
  }
  assert.deepEqual(ZONES.map((z) => z.slug), Object.keys(TAXONOMY));
});

test("backpack slot only covers backpacks; tent slot excludes stakes", () => {
  assert.deepEqual(slotForCategory("backpacks").categories, ["backpacks"]);
  const tent = slotForCategory("tents");
  assert.ok(!tent.categories.includes("stakes-guylines"));
  assert.ok(!tent.categories.includes("stoves"));
});

function item(id: string, slug: string, top: string): GearItem {
  return { id, category: { slug, top_slug: top } } as unknown as GearItem;
}

test("items group into slots and coverage counts zones, not items", () => {
  const items = [
    item("a", "backpacks", "backpack"),
    item("b", "backpacks", "backpack"),
    item("c", "quilts", "sleep"),
    item("d", "sleep", "sleep"), // custom item filed at the zone level
  ];
  const grouped = groupItemsBySlot(items);
  assert.deepEqual(grouped.get("backpack")?.map((i) => i.id), ["a", "b"]);
  assert.deepEqual(grouped.get("sleeping-bag")?.map((i) => i.id), ["c"]);
  assert.deepEqual(grouped.get("pillow")?.map((i) => i.id), ["d"]);
  assert.deepEqual(zoneCoverage(items), { filled: 2, total: 10 });
  assert.deepEqual(zoneCoverage([]), { filled: 0, total: 10 });
});


test("seven core showcase slots; everything else is under More gear", () => {
  assert.deepEqual(CORE_SLOTS.map((slot) => slot.key), [
    "backpack", "tent", "sleeping-bag", "sleeping-pad", "stove", "footwear", "rain-jacket",
  ]);
  assert.ok(CORE_SLOTS.every((slot) => slot.core));
  const more = MORE_ZONES.flatMap((zone) => zone.slots);
  assert.ok(more.every((slot) => !slot.core));
  assert.equal(more.length + CORE_SLOTS.length, ALL_SLOTS.length);
  // The stove picker only offers stoves, not fuel or accessories.
  assert.deepEqual(slotForCategory("stoves").categories, ["stoves"]);
  assert.equal(slotForCategory("fuel-accessories").key, "cookware");
});
