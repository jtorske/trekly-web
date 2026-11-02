import test from "node:test";
import assert from "node:assert/strict";
import type { GearItem } from "../../lib/gearApi.ts";
import { bigThreeStatus, carryOf, packClassFor, packSummary } from "./baseWeight.ts";
import { MORE_GEAR, groupItemsByPlacement, matPlacement, matSlotFor } from "./slots.ts";
import { PACK_CLASSES } from "./weightConfig.ts";

function item(
  id: string,
  slug: string,
  top: string,
  grams: number | null,
  extra: Partial<GearItem> = {},
): GearItem {
  return {
    id,
    category: { slug, top_slug: top },
    quantity: 1,
    weight: { effective_g: grams },
    carry: null,
    mat_slot: null,
    ...extra,
  } as unknown as GearItem;
}

test("pack classes follow the configured thresholds, exclusive upper limits", () => {
  assert.equal(packClassFor(0).key, "super-ultralight");
  assert.equal(packClassFor(4499).key, "super-ultralight");
  assert.equal(packClassFor(4500).key, "ultralight");
  assert.equal(packClassFor(8999).key, "ultralight");
  assert.equal(packClassFor(9000).key, "lightweight");
  assert.equal(packClassFor(13500).key, "traditional");
  assert.equal(packClassFor(40000).key, "traditional");
  assert.equal(PACK_CLASSES.at(-1)!.underGrams, null);
});

test("boots are worn by default; the owner's choice wins", () => {
  assert.equal(carryOf(item("b", "trail-runners", "footwear", 600)), "worn");
  assert.equal(carryOf(item("b", "trail-runners", "footwear", 600, { carry: "packed" })), "packed");
  assert.equal(carryOf(item("c", "camp-shoes", "footwear", 200)), "packed");
  assert.equal(carryOf(item("t", "tents", "shelter", 1000)), "packed");
});

test("base weight leaves out worn and consumable items and sums by zone", () => {
  const summary = packSummary([
    item("pack", "backpacks", "backpack", 900),
    item("tent", "tents", "shelter", 1100),
    item("bag", "quilts", "sleep", 600),
    item("pad", "sleeping-pads", "sleep", 400),
    item("stakes", "stakes-guylines", "shelter", 25, { quantity: 8 }),
    item("stove", "stoves", "cooking", 80),
    item("boots", "hiking-boots", "footwear", 1200),
    item("fuel", "fuel-accessories", "cooking", 230, { carry: "consumable" }),
    item("jacket", "rainwear", "clothing", 300, { carry: "worn" }),
  ]);
  assert.equal(summary.baseGrams, 900 + 1100 + 600 + 400 + 200 + 80);
  assert.equal(summary.wornGrams, 1500);
  assert.equal(summary.consumableGrams, 230);
  assert.equal(summary.bigThreeGrams, 900 + 1300 + 1000);
  assert.deepEqual(
    summary.zones.map((zone) => [zone.slug, zone.grams, zone.bigThree]),
    [["backpack", 900, true], ["shelter", 1300, true], ["sleep", 1000, true], ["cooking", 80, false]],
  );
  assert.equal(summary.packClass?.key, "super-ultralight");
  assert.equal(summary.missingBase, 0);
});

const BIG_THREE = [
  item("pack", "backpacks", "backpack", 900),
  item("tent", "tents", "shelter", 1100),
  item("bag", "quilts", "sleep", 600),
  item("pad", "sleeping-pads", "sleep", 400),
];

test("a packed item with no weight means no total and no class", () => {
  const summary = packSummary([...BIG_THREE, item("x", "misc", "accessories", null)]);
  assert.equal(summary.missingBase, 1);
  assert.equal(summary.packClass, null);
  // A worn item with no weight doesn't hold the base weight back.
  const worn = packSummary([...BIG_THREE, item("b", "hiking-boots", "footwear", null)]);
  assert.equal(worn.missingBase, 0);
  assert.equal(worn.packClass?.key, "super-ultralight");
  assert.equal(packSummary([]).packClass, null);
});

test("no class until the Big Three are complete; the base weight still adds up", () => {
  const noSleep = packSummary(BIG_THREE.slice(0, 2));
  assert.equal(noSleep.packClass, null);
  assert.equal(noSleep.baseGrams, 2000);
  assert.deepEqual(noSleep.bigThree, { have: 2, total: 3, missing: "sleeping bag and pad" });
  assert.equal(packSummary(BIG_THREE).bigThree.missing, null);
  assert.equal(packSummary(BIG_THREE).packClass?.key, "super-ultralight");
});

test("missing Big Three pieces are named in plain words", () => {
  const missing = (items: GearItem[]) => bigThreeStatus(items).missing;
  assert.equal(missing([]), "pack, shelter, sleeping bag and pad");
  assert.equal(missing(BIG_THREE.filter((i) => i.id !== "pad")), "sleeping pad");
  assert.equal(missing(BIG_THREE.filter((i) => i.id !== "bag")), "sleeping bag");
  assert.equal(missing(BIG_THREE.filter((i) => i.id !== "tent" && i.id !== "pad")), "shelter and sleeping pad");
  // A bag without a pad is not a sleep system yet.
  assert.equal(bigThreeStatus(BIG_THREE.filter((i) => i.id !== "pad")).have, 2);
  // Presence goes by category, not where the item sits on the mat.
  const moved = BIG_THREE.map((i) => (i.id === "tent" ? { ...i, mat_slot: "more" } : i));
  assert.equal(bigThreeStatus(moved).have, 3);
});

test("mat placement follows mat_slot, falling back to the category's slot", () => {
  const tent = item("t", "tents", "shelter", 1000);
  const pillow = item("p", "pillows", "sleep", 80);
  assert.equal(matPlacement(tent), "tent");
  assert.equal(matPlacement(pillow), MORE_GEAR);
  assert.equal(matPlacement({ ...pillow, mat_slot: "backpack" }), "backpack");
  assert.equal(matPlacement({ ...tent, mat_slot: MORE_GEAR }), MORE_GEAR);
  // A slot that no longer exists (or a More gear slot) never hides the item.
  assert.equal(matPlacement({ ...tent, mat_slot: "spaceship" }), "tent");
  assert.equal(matPlacement({ ...pillow, mat_slot: "pillow" }), MORE_GEAR);

  assert.equal(matSlotFor(tent, "tent"), null);
  assert.equal(matSlotFor(tent, MORE_GEAR), MORE_GEAR);
  assert.equal(matSlotFor(tent, "backpack"), "backpack");
  assert.equal(matSlotFor(pillow, MORE_GEAR), null);
  assert.equal(matSlotFor(pillow, "sleeping-pad"), "sleeping-pad");

  const grouped = groupItemsByPlacement([tent, pillow, { ...pillow, id: "p2", mat_slot: "tent" }]);
  assert.deepEqual(grouped.get("tent")?.map((i) => i.id), ["t", "p2"]);
  assert.deepEqual(grouped.get(MORE_GEAR)?.map((i) => i.id), ["p"]);
});
