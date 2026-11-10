import test from "node:test";
import assert from "node:assert/strict";
import { REGIONS } from "./onboarding.ts";
import { PROVINCES } from "./provinces.ts";
import { PROVINCE_CENTRES, orderRegions, regionChips, sortOrigin } from "./regionOrder.ts";
import { formatWholeDistance } from "./units.ts";

const slugs = (chips: { region: { slug: string } }[]) => chips.map((chip) => chip.region.slug);
const CANMORE = { lat: 51.09, lon: -115.36 };
const HALIFAX = { lat: 44.65, lon: -63.58 };

test("every park has a centre point inside Canada", () => {
  for (const region of REGIONS) {
    assert.ok(region.centre.lat > 41 && region.centre.lat < 84, region.slug);
    assert.ok(region.centre.lon > -142 && region.centre.lon < -52, region.slug);
  }
});

test("every province and territory has a centre", () => {
  for (const province of PROVINCES) assert.ok(PROVINCE_CENTRES[province.code], province.code);
});

// --------------------------------------------------- what we measure from

test("permission granted: the browser's location wins over the home province", () => {
  assert.deepEqual(sortOrigin(CANMORE, "NS"), { kind: "here", point: CANMORE });
});

test("no location: the centre of the home province", () => {
  assert.deepEqual(sortOrigin(null, "AB"), { kind: "home", province: "AB", point: PROVINCE_CENTRES.AB });
});

test("neither: no home, Outside Canada or Prefer not to say means no sorting", () => {
  for (const home of [null, undefined, "", "outside", "none"]) assert.equal(sortOrigin(null, home), null, String(home));
});

// ---------------------------------------------------------- the order

test("permission granted: nearest to them first, with distances", () => {
  const chips = orderRegions(REGIONS, sortOrigin(CANMORE, null));
  assert.deepEqual(slugs(chips).slice(0, 3), ["assiniboine", "kananaskis", "kootenay"]);
  assert.equal(slugs(chips).at(-1), "gros-morne");
  for (let i = 1; i < chips.length; i++) assert.ok(chips[i - 1].km! <= chips[i].km!, "nearest first");
  // From the East Coast, the Atlantic parks lead.
  assert.deepEqual(slugs(orderRegions(REGIONS, sortOrigin(HALIFAX, "AB"))).slice(0, 2), ["cape-breton", "forillon"]);
});

test("home province only: nearest to its centre first", () => {
  const fromOntario = slugs(orderRegions(REGIONS, sortOrigin(null, "ON")));
  assert.equal(fromOntario[0], "pukaskwa");
  assert.ok(fromOntario.indexOf("algonquin") < fromOntario.indexOf("banff"));
  const fromBC = slugs(orderRegions(REGIONS, sortOrigin(null, "BC")));
  assert.ok(fromBC.indexOf("robson") < fromBC.indexOf("gros-morne"));
  assert.ok(fromBC.slice(0, 6).every((slug) => REGIONS.find((r) => r.slug === slug)!.province !== "NL"));
});

test("neither: the usual order, and no distances", () => {
  const chips = orderRegions(REGIONS, null);
  assert.deepEqual(slugs(chips), REGIONS.map((r) => r.slug));
  assert.ok(chips.every((chip) => chip.km === null));
});

test("distances read in the person's units", () => {
  const banff = orderRegions(REGIONS, sortOrigin(CANMORE, null)).find((chip) => chip.region.slug === "banff")!;
  assert.match(formatWholeDistance(banff.km!, "metric"), /^\d+ km$/);
  assert.match(formatWholeDistance(banff.km!, "imperial"), /^\d+ mi$/);
  assert.ok(banff.km! > 20 && banff.km! < 120, String(banff.km));
});

// ------------------------------------------------- search and picked chips

test("picked chips stay at the top, whatever the search", () => {
  const origin = sortOrigin(null, "AB");
  const chips = regionChips({ query: "ontario", pinned: ["gros-morne", "banff"], origin, provinceNames: { ON: "Ontario" } });
  // Picks first (nearest first among them), then only the search's matches.
  assert.deepEqual(slugs(chips.pinned), ["banff", "gros-morne"]);
  assert.ok(chips.others.length > 0);
  assert.ok(chips.others.every((chip) => chip.region.province === "ON"));
  for (let i = 1; i < chips.others.length; i++) assert.ok(chips.others[i - 1].km! <= chips.others[i].km!);
});

test("with no search, every park shows once", () => {
  const chips = regionChips({ query: "", pinned: ["yoho"], origin: null });
  assert.deepEqual(slugs(chips.pinned), ["yoho"]);
  assert.equal(chips.pinned.length + chips.others.length, REGIONS.length);
  assert.ok(!slugs(chips.others).includes("yoho"));
});

test("a search that matches nothing leaves only the picks", () => {
  const chips = regionChips({ query: "narnia", pinned: ["banff"], origin: null });
  assert.deepEqual(slugs(chips.pinned), ["banff"]);
  assert.deepEqual(chips.others, []);
});
