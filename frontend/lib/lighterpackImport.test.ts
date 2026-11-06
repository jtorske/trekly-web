import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { confirmRequest, countChoices, initialChoices, type ImportRow } from "./lighterpackImport.ts";
import type { ProductSummary } from "./gearApi.ts";

const product = (id: string) => ({ id, display_name: `Product ${id}` }) as ProductSummary;

const row = (index: number, more: Partial<ImportRow> = {}): ImportRow => ({
  index,
  name: `Item ${index}`,
  lighterpack_category: "Shelter",
  description: "",
  quantity: 1,
  weight: { value: 540, unit: "g" },
  carry: null,
  match: null,
  alternatives: [],
  category: "misc",
  include: true,
  ...more,
});

const rows = [
  row(0, { match: { product: product("tent"), confidence: "high", score: 0.95 } }),
  row(1, {
    match: { product: product("pad-a"), confidence: "low", score: 0.5 },
    alternatives: [{ product: product("pad-b"), confidence: "low", score: 0.4 }],
  }),
  row(2, { name: "Homemade windscreen", description: "foil", category: "fuel-accessories", weight: { value: 0.4, unit: "oz" } }),
  row(3, { name: "Trail mix", carry: "consumable", include: false, quantity: 2 }),
];

describe("LighterPack import choices", () => {
  it("starts from the proposed match, or the hiker's own item without one", () => {
    const choices = initialChoices(rows);
    assert.deepEqual([...choices.values()].map((c) => c.product), ["tent", "pad-a", "custom", "custom"]);
    assert.equal(choices.get(3)!.include, false);
  });

  it("sends only included rows: catalogue products by id, the rest as named items", () => {
    const request = confirmRequest("import-1", rows, initialChoices(rows));
    assert.equal(request.import_id, "import-1");
    assert.deepEqual(request.items, [
      { index: 0, quantity: 1, weight: { value: "540", unit: "g" }, carry: null, product_id: "tent" },
      { index: 1, quantity: 1, weight: { value: "540", unit: "g" }, carry: null, product_id: "pad-a" },
      {
        index: 2, quantity: 1, weight: { value: "0.4", unit: "oz" }, carry: null,
        name: "Homemade windscreen", category: "fuel-accessories", notes: "foil",
      },
    ]);
  });

  it("follows the hiker's changes", () => {
    const choices = initialChoices(rows);
    choices.set(1, { ...choices.get(1)!, product: "pad-b" });
    choices.set(0, { ...choices.get(0)!, product: "custom", category: "tents" });
    choices.set(3, { ...choices.get(3)!, include: true });
    const items = confirmRequest("x", rows, choices).items;
    assert.equal(items[0].product_id, undefined);
    assert.equal(items[0].category, "tents");
    assert.equal(items[1].product_id, "pad-b");
    assert.equal(items[3].carry, "consumable");
    assert.equal(items[3].quantity, 2);
  });

  it("counts what will be added and the matches to check", () => {
    assert.deepEqual(countChoices(rows, initialChoices(rows)), { included: 3, catalogue: 2, own: 1, toCheck: 1 });
  });
});
