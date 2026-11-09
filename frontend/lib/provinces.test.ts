import test from "node:test";
import assert from "node:assert/strict";
import { OUTSIDE, OUTSIDE_CANADA, OUTSIDE_CANADA_DESIGNS, PROVINCES, homeLabel, province, provinceOptions } from "./provinces.ts";

test("all 13 provinces and territories, once each", () => {
  const codes = PROVINCES.map((p) => p.code);
  assert.equal(new Set(codes).size, 13);
  assert.deepEqual([...codes].sort(), ["AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"]);
  assert.equal(PROVINCES.filter((p) => p.kind === "territory").length, 3);
});

test("every badge has its own colour and a motif to draw", () => {
  assert.equal(new Set(PROVINCES.map((p) => p.colour)).size, 13);
  for (const p of PROVINCES) {
    assert.match(p.colour, /^#[0-9a-f]{6}$/);
    assert.ok(p.shapes.length > 0 && p.shapes.every((shape) => shape.d.startsWith("M") && !shape.d.includes("NaN")), p.code);
  }
});

test("lookups and labels", () => {
  assert.equal(province("NU")?.name, "Nunavut");
  assert.equal(province(null), null);
  assert.equal(province("XX"), null);
  assert.equal(homeLabel(province("AB")!), "Home province");
  assert.equal(homeLabel(province("YT")!), "Home territory");
});

test("the menu lists provinces then territories, A–Z, then Outside Canada", () => {
  const [provinces, territories, elsewhere] = provinceOptions();
  assert.deepEqual(elsewhere.options, [OUTSIDE]);
  assert.equal(provinces.options.length, 10);
  assert.deepEqual(territories.options.map((p) => p.name), ["Northwest Territories", "Nunavut", "Yukon"]);
  assert.equal(provinces.options[0].name, "Alberta");
  assert.equal(provinces.options.at(-1)?.name, "Saskatchewan");
});

test("Outside Canada is a home with a badge of its own in the same style", () => {
  assert.equal(OUTSIDE_CANADA, "outside");
  assert.equal(province("outside"), OUTSIDE);
  assert.equal(OUTSIDE.name, "Outside Canada");
  assert.equal(homeLabel(OUTSIDE), "Home");
  // Not one of the 13, so nothing that counts provinces counts it.
  assert.ok(!PROVINCES.some((p) => p.code === OUTSIDE_CANADA));
  for (const design of Object.values(OUTSIDE_CANADA_DESIGNS)) {
    assert.equal(design.code, OUTSIDE_CANADA);
    assert.ok(design.badgeName && design.badgeFoot);
    assert.match(design.colour, /^#[0-9a-f]{6}$/);
    assert.ok(!PROVINCES.some((p) => p.colour === design.colour), "a colour no province uses");
    assert.ok(design.shapes.length > 0 && design.shapes.every((shape) => shape.d.startsWith("M") && !shape.d.includes("NaN")));
  }
});
