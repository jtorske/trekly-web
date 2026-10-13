import test from "node:test";
import assert from "node:assert/strict";
import { formatCapacity, formatSpecValue, formatWeight } from "./units.ts";

test("weights format without changing the canonical value", () => {
  assert.equal(formatWeight(83), "2.9 oz");
  assert.equal(formatWeight(1304.078), "2 lb 14 oz");
  assert.equal(formatWeight(907.185), "2 lb");
  assert.equal(formatWeight(453.1), "1 lb");
  assert.equal(formatWeight(354.369), "12.5 oz");
  assert.equal(formatWeight(83, "metric"), "83 g");
  assert.equal(formatWeight(1304.078, "metric"), "1.3 kg");
  assert.equal(formatWeight(0), "0 oz");
});

test("capacities", () => {
  assert.equal(formatCapacity(60000), "60 L");
  assert.equal(formatCapacity(900), "30.4 fl oz");
  assert.equal(formatCapacity(900, "metric"), "900 mL");
  assert.equal(formatCapacity(1000, "metric"), "1 L");
});

test("spec rows", () => {
  assert.equal(formatSpecValue(true, null), "Yes");
  assert.equal(formatSpecValue(7.6, "cm"), "3 in");
  assert.equal(formatSpecValue(7.6, "cm", "metric"), "7.6 cm");
  assert.equal(formatSpecValue(-1, "c"), "30 °F");
  assert.equal(formatSpecValue(2, "persons"), "2 people");
  assert.equal(formatSpecValue(4.5, null), "4.5");
  assert.equal(formatSpecValue("canister", null), "canister");
});
