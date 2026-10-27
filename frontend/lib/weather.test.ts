import test from "node:test";
import assert from "node:assert/strict";
import {
  clockTime,
  dayName,
  describeWeather,
  environmentCanadaUrl,
  shortDate,
  showAvalancheLink,
  todayIn,
} from "./weather.ts";
import { formatPrecip, formatSnow, formatWind } from "./units.ts";

test("WMO codes map to a label and an icon", () => {
  assert.deepEqual(describeWeather(0), { label: "Clear", icon: "clear" });
  assert.equal(describeWeather(45).icon, "fog");
  assert.equal(describeWeather(66).icon, "freezing");
  assert.equal(describeWeather(75).label, "Heavy snow");
  assert.equal(describeWeather(86).icon, "snow");
  assert.equal(describeWeather(99).icon, "storm");
  assert.equal(describeWeather(null).label, "Unknown");
  assert.equal(describeWeather(12345).label, "Unknown");
});

test("wind, rain and snow follow the units setting", () => {
  assert.equal(formatWind(24.6, "metric"), "25 km/h");
  assert.equal(formatWind(24.6, "imperial"), "15 mph");
  assert.equal(formatPrecip(2.44, "metric"), "2.4 mm");
  assert.equal(formatPrecip(2.44, "imperial"), "0.1 in");
  assert.equal(formatPrecip(0, "metric"), "0 mm");
  assert.equal(formatPrecip(0.05, "metric"), "trace");
  assert.equal(formatPrecip(0.1, "imperial"), "trace");
  assert.equal(formatSnow(3, "metric"), "3 cm");
  assert.equal(formatSnow(3, "imperial"), "1.2 in");
  assert.equal(formatSnow(0.07, "imperial"), "trace");
  assert.equal(formatSnow(0.04, "metric"), "trace");
});

test("days are named at the trail, with today called out", () => {
  assert.equal(dayName("2026-10-26", "2026-10-26"), "Today");
  assert.equal(dayName("2026-10-27", "2026-10-26"), "Tue");
  assert.equal(shortDate("2026-10-27"), "Oct 27");
  // 05:30 UTC on Oct 27 is still Oct 26 in Edmonton.
  assert.equal(todayIn("America/Edmonton", new Date("2026-10-27T05:30:00Z")), "2026-10-26");
  assert.match(todayIn("Not/AZone"), /^\d{4}-\d{2}-\d{2}$/);
});

test("sunrise and sunset read as local clock times", () => {
  assert.equal(clockTime("2026-10-26T08:28"), "8:28 a.m.");
  assert.equal(clockTime("2026-10-26T18:05"), "6:05 p.m.");
  assert.equal(clockTime("2026-10-26T00:15"), "12:15 a.m.");
  assert.equal(clockTime("garbage"), "");
});

test("official forecast links", () => {
  assert.equal(environmentCanadaUrl(51.41592, -116.2112), "https://weather.gc.ca/en/location/index.html?coords=51.416,-116.211");
  assert.equal(showAvalancheLink("AB", "CA", new Date(2026, 9, 1)), true);
  assert.equal(showAvalancheLink("BC", "CA", new Date(2027, 4, 31)), true);
  assert.equal(showAvalancheLink("BC", "CA", new Date(2026, 5, 1)), false);
  assert.equal(showAvalancheLink("ON", "CA", new Date(2026, 11, 1)), false);
  assert.equal(showAvalancheLink("WA", "US", new Date(2026, 11, 1)), false);
});
