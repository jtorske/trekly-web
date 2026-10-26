import test from "node:test";
import assert from "node:assert/strict";
import {
  formatCapacity,
  formatDegrees,
  formatDistance,
  formatElevation,
  formatRouteDistance,
  formatSpecValue,
  formatTemperature,
  formatTrailDistance,
  formatTrailElevation,
  formatWeight,
  preferUnitSystem,
} from "./units.ts";

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

test("trail measurements default to metric", () => {
  assert.equal(formatElevation(2135), "2,135 m");
  assert.equal(formatElevation(2135, "imperial"), "7,005 ft");
  assert.equal(formatDistance(12.43), "12.4 km");
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

test("dual-unit spec text puts the reader's system first", () => {
  assert.equal(preferUnitSystem("9 x 4.1 in (23 x 10 cm)", "metric"), "23 x 10 cm (9 x 4.1 in)");
  assert.equal(preferUnitSystem("9 x 4.1 in (23 x 10 cm)", "imperial"), "9 x 4.1 in (23 x 10 cm)");
  assert.equal(preferUnitSystem("34 x 26 x 11 cm (13 x 10 x 4 in)", "imperial"), "13 x 10 x 4 in (34 x 26 x 11 cm)");
  assert.equal(preferUnitSystem("3 lb 9 oz (1.61 kg)", "metric"), "1.61 kg (3 lb 9 oz)");
  assert.equal(
    preferUnitSystem("8.7 in diameter x 12.7 in tall (22.1 x 32.3 cm)", "metric"),
    "22.1 x 32.3 cm (8.7 in diameter x 12.7 in tall)",
  );
  assert.equal(formatSpecValue("9 x 4.1 in (23 x 10 cm)", null, "metric"), "23 x 10 cm (9 x 4.1 in)");
});

test("other spec text is left alone", () => {
  for (const text of ["32-Foot Bear Spray (8.1 oz.)", "Canister (sold separately)", "19-22 in", "Mummy"]) {
    assert.equal(preferUnitSystem(text, "metric"), text);
  }
});
