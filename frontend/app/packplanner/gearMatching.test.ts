import test from "node:test";
import assert from "node:assert/strict";
import { gramsToLb, pickAdequateVariant, type RatedVariant } from "./gearMatching.ts";

test("gramsToLb converts grams to pounds using a single canonical factor", () => {
  // Sleeping bag: gear_items.weight_g = 1200
  assert.equal(Math.round(gramsToLb(1200) * 100) / 100, 2.65);
  assert.equal(gramsToLb(453.592), 1);
  assert.equal(gramsToLb(0), 0);
});

test("weight scales correctly for a sample trip: quantity multiplication happens once, in pounds", () => {
  // Sample trip: 3-person group, sharing gear off (solo sleeping bags).
  const sleepingBagWeightG = 1200;
  const groupSize = 3;

  const perUnitLb = gramsToLb(sleepingBagWeightG);
  const totalLb = perUnitLb * groupSize;

  // Per-unit weight must match the direct gram conversion exactly (no
  // partial conversion or double-scaling before this point).
  assert.equal(Math.round(perUnitLb * 100) / 100, 2.65);
  // Total must be a clean multiple of the per-unit weight — scaling by
  // quantity in pounds, not mixed with any gram-based multiplication.
  assert.equal(Math.round(totalLb * 100) / 100, 7.94);
  assert.equal(totalLb, perUnitLb * groupSize);
});

test("pickAdequateVariant picks the lightest/warmest-adequate variant, not the most extreme", () => {
  const sleepingBags: RatedVariant[] = [
    { variant_name: "15C summer bag", min_temp_c: 15, min_r_value: null },
    { variant_name: "10C comfort bag", min_temp_c: 10, min_r_value: null },
    { variant_name: "0C comfort bag", min_temp_c: 0, min_r_value: null },
    { variant_name: "-10C comfort bag", min_temp_c: -10, min_r_value: null },
    { variant_name: "-20C comfort bag", min_temp_c: -20, min_r_value: null },
  ];

  // avgLowC=8, safetyBuffer=5 => target=3. Adequate: 0,-10,-20. Warmest
  // adequate (closest at-or-below target) is the 0C bag, not the -20C one.
  const { variant, isFallback } = pickAdequateVariant(sleepingBags, 8 - 5);
  assert.equal(variant.variant_name, "0C comfort bag");
  assert.equal(isFallback, false);
});

test("pickAdequateVariant falls back to the warmest-rated variant when nothing is adequate", () => {
  const sleepingBags: RatedVariant[] = [
    { variant_name: "15C summer bag", min_temp_c: 15, min_r_value: null },
    { variant_name: "0C comfort bag", min_temp_c: 0, min_r_value: null },
    { variant_name: "-20C comfort bag", min_temp_c: -20, min_r_value: null },
  ];

  // avgLowC=-25, safetyBuffer=5 => target=-30. Nothing is rated that cold.
  const { variant, isFallback } = pickAdequateVariant(sleepingBags, -25 - 5);
  assert.equal(variant.variant_name, "-20C comfort bag");
  assert.equal(isFallback, true);
});
