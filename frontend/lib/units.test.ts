import test from "node:test";
import assert from "node:assert/strict";
import {
  bottleCapacityFilters,
  formatCapacity,
  formatDegrees,
  formatDistance,
  formatElevation,
  formatLength,
  formatPrecip,
  formatRouteDistance,
  formatSnow,
  formatSpecValue,
  formatTemperature,
  formatTrailDistance,
  formatTrailElevation,
  formatWeight,
  formatWholeDistance,
  formatWind,
  gramsFromInput,
  gramsToInput,
  legacyUnitsToMigrate,
  resolveUnits,
  specTextInSystem,
  weightFilters,
  weightInputUnit,
} from "./units.ts";

test("conversions and rounding", () => {
  assert.equal(formatDistance(6.6, "imperial"), "4.1 mi");
  assert.equal(formatDistance(6.6), "6.6 km");
  assert.equal(formatElevation(2135, "imperial"), "7,005 ft");
  assert.equal(formatElevation(2135), "2,135 m");
  assert.equal(formatTemperature(-5, "imperial"), "23°F");
  assert.equal(formatTemperature(-5), "-5°C");
  assert.equal(formatWind(24.6), "25 km/h");
  assert.equal(formatWind(24.6, "imperial"), "15 mph");
  assert.equal(formatPrecip(2.44), "2.4 mm");
  assert.equal(formatPrecip(2.44, "imperial"), "0.1 in");
  assert.equal(formatSnow(3), "3 cm");
  assert.equal(formatSnow(3, "imperial"), "1.2 in");
  assert.equal(formatLength(23), "23 cm");
  assert.equal(formatLength(23, "imperial"), "9.1 in");
});

test("whole distances for goals", () => {
  assert.equal(formatWholeDistance(100), "100 km");
  assert.equal(formatWholeDistance(100, "imperial"), "62 mi");
  assert.equal(formatWholeDistance(1000, "imperial"), "621 mi");
});

test("everything defaults to metric", () => {
  assert.equal(formatWeight(83), "83 g");
  assert.equal(formatCapacity(900), "900 mL");
  assert.equal(formatSpecValue(7.6, "cm"), "7.6 cm");
  assert.equal(formatSpecValue(-1, "c"), "-1 °C");
  assert.equal(formatWind(10), "10 km/h");
  assert.equal(formatDistance(12.43), "12.4 km");
});

test("trail distance hides unknown lengths and falls back without a route type", () => {
  assert.equal(formatTrailDistance(8.66, "out_and_back"), "8.7 km round trip");
  assert.equal(formatTrailDistance(5.2, null, "imperial"), "3.2 mi");
  assert.equal(formatTrailDistance(null, "loop"), null);
  assert.equal(formatTrailDistance(undefined, null), null);
  assert.equal(formatTrailDistance(0, "loop"), null);
  assert.equal(formatTrailDistance(-3, "loop"), null);
  assert.equal(formatTrailDistance(Number.NaN, "loop"), null);
});

test("trail elevation hides unknown, zero and invalid values", () => {
  assert.equal(formatTrailElevation(650), "650 m");
  assert.equal(formatTrailElevation(650, "imperial"), "2,133 ft");
  assert.equal(formatTrailElevation(null), null);
  assert.equal(formatTrailElevation(0), null);
  assert.equal(formatTrailElevation(Number.POSITIVE_INFINITY), null);
});

test("trail measurements", () => {
  assert.equal(formatDistance(12.43, "imperial"), "7.7 mi");
  assert.equal(formatDistance(75), "75 km");
  assert.equal(formatDistance(336.4), "336 km");
  assert.equal(formatRouteDistance(8.66, "out_and_back"), "8.7 km round trip");
  assert.equal(formatRouteDistance(75.9, "point_to_point"), "75.9 km one way");
  assert.equal(formatRouteDistance(5.2, "loop", "imperial"), "3.2 mi loop");
  assert.equal(formatDegrees(-3.6), "-4°");
  assert.equal(formatDegrees(-3.6, "imperial"), "26°");
  assert.equal(formatTemperature(12.4), "12°C");
  assert.equal(formatTemperature(12.4, "imperial"), "54°F");
});

test("weights format without changing the canonical value", () => {
  assert.equal(formatWeight(83, "imperial"), "2.9 oz");
  assert.equal(formatWeight(1304.078, "imperial"), "2 lb 14 oz");
  assert.equal(formatWeight(907.185, "imperial"), "2 lb");
  assert.equal(formatWeight(453.1, "imperial"), "1 lb");
  assert.equal(formatWeight(354.369, "imperial"), "12.5 oz");
  assert.equal(formatWeight(1304.078), "1.3 kg");
  assert.equal(formatWeight(0, "imperial"), "0 oz");
});

test("capacities", () => {
  assert.equal(formatCapacity(60000, "imperial"), "60 L");
  assert.equal(formatCapacity(900, "imperial"), "30.4 fl oz");
  assert.equal(formatCapacity(1000), "1 L");
});

test("spec rows", () => {
  assert.equal(formatSpecValue(true, null), "Yes");
  assert.equal(formatSpecValue(7.6, "cm", "imperial"), "3 in");
  assert.equal(formatSpecValue(-1, "c", "imperial"), "30 °F");
  assert.equal(formatSpecValue(2, "persons"), "2 people");
  assert.equal(formatSpecValue(4.5, null), "4.5");
  assert.equal(formatSpecValue("canister", null), "canister");
});

test("dual-unit spec text shows only the reader's system", () => {
  assert.equal(specTextInSystem("9 x 4.1 in (23 x 10 cm)", "metric"), "23 x 10 cm");
  assert.equal(specTextInSystem("9 x 4.1 in (23 x 10 cm)", "imperial"), "9 x 4.1 in");
  assert.equal(specTextInSystem("34 x 26 x 11 cm (13 x 10 x 4 in)", "imperial"), "13 x 10 x 4 in");
  assert.equal(specTextInSystem("3 lb 9 oz (1.61 kg)", "metric"), "1.61 kg");
  assert.equal(specTextInSystem("8.7 in diameter x 12.7 in tall (22.1 x 32.3 cm)", "metric"), "22.1 x 32.3 cm");
  assert.equal(formatSpecValue("9 x 4.1 in (23 x 10 cm)", null, "metric"), "23 x 10 cm");
});

test("measurement-only spec text converts to the reader's system", () => {
  assert.equal(specTextInSystem("19-22 in", "metric"), "48.3-55.9 cm");
  assert.equal(specTextInSystem("19-22 in", "imperial"), "19-22 in");
  assert.equal(
    specTextInSystem("S 15-18 in, M 18-21 in, L 21-24 in, XL 24+ in", "metric"),
    "S 38.1-45.7 cm, M 45.7-53.3 cm, L 53.3-61 cm, XL 61+ cm",
  );
  assert.equal(specTextInSystem("80 x 65 x 265 mm", "imperial"), "3.1 x 2.6 x 10.4 in");
  assert.equal(specTextInSystem("39-53 cm", "imperial"), "15.4-20.9 in");
  assert.equal(specTextInSystem("2.9 oz", "metric"), "82 g");
  assert.equal(specTextInSystem("3 lb 9 oz", "metric"), "1.62 kg");
});

test("prose in spec text is left as written", () => {
  for (const text of [
    "32-Foot Bear Spray (8.1 oz.)",
    "Canister (sold separately)",
    "Mummy",
    "Fixed-length Z-pole, sold in 105-130 cm lengths",
    "PVC-free 300D 18 oz polyurethane-coated polyester",
    "Vertice waterproof breathable fabric (1.50 oz/sqyd)",
  ]) {
    assert.equal(specTextInSystem(text, "metric"), text);
    assert.equal(specTextInSystem(text, "imperial"), text);
  }
});

test("gear filters are labelled in one system", () => {
  assert.deepEqual(
    weightFilters("metric").map((f) => f.label),
    ["Any weight", "Under 250 g", "Under 500 g", "Under 1 kg", "Under 1.5 kg"],
  );
  assert.deepEqual(
    weightFilters("imperial").map((f) => f.label),
    ["Any weight", "Under 8 oz", "Under 1 lb", "Under 2 lb", "Under 3 lb"],
  );
  assert.deepEqual(bottleCapacityFilters("metric").map((f) => f.label), ["Any size", "Up to 1 L", "Over 1 L"]);
  assert.deepEqual(bottleCapacityFilters("imperial").map((f) => f.label), ["Any size", "Up to 32 fl oz", "Over 32 fl oz"]);
});

test("weight entry is typed in the reader's units and stored in grams", () => {
  assert.equal(weightInputUnit("metric"), "g");
  assert.equal(weightInputUnit("imperial"), "oz");
  assert.equal(weightInputUnit("metric", "kg"), "kg");
  assert.equal(weightInputUnit("metric", "oz"), "g");
  assert.equal(gramsFromInput("12.5", "oz"), 354.369);
  assert.equal(gramsFromInput("1.2", "kg"), 1200);
  assert.equal(gramsFromInput("", "g"), null);
  assert.equal(gramsFromInput("-1", "g"), null);
  assert.equal(gramsFromInput("abc", "g"), null);
  assert.equal(gramsToInput(354.369, "oz"), "12.5");
  assert.equal(gramsToInput(354.369, "g"), "354.4");
});

test("the account setting: guests see metric, accounts see their choice", () => {
  assert.equal(resolveUnits(false, "imperial"), "metric");
  assert.equal(resolveUnits(true, null), "metric");
  assert.equal(resolveUnits(true, "imperial"), "imperial");
  assert.equal(resolveUnits(true, "metric"), "metric");
});

test("a per-browser choice from before is carried over once", () => {
  assert.equal(legacyUnitsToMigrate(null, "imperial"), "imperial");
  assert.equal(legacyUnitsToMigrate(null, "metric"), "metric");
  assert.equal(legacyUnitsToMigrate(null, null), null);
  assert.equal(legacyUnitsToMigrate(null, "nonsense"), null);
  // The account's own setting wins over an old browser value.
  assert.equal(legacyUnitsToMigrate("metric", "imperial"), null);
});
