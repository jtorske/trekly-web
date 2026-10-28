/**
 * The one place the app converts and formats measurements. Canonical values
 * from the API are metric (km, m, grams, millilitres, centimetres, °C, km/h,
 * mm of rain, cm of snow); these functions only format them for display —
 * they never round the stored value. Components must format through here
 * rather than doing their own conversions (lib/unitsUsage.test.ts checks).
 *
 * Metric is the default everywhere; signed-in users can switch to imperial
 * in Settings (see useUnits). Only one system is ever shown at a time.
 */

import type { RouteType } from "./trailsApi";

export type UnitSystem = "imperial" | "metric";
export type WeightUnit = "g" | "kg" | "oz" | "lb";

export const DEFAULT_UNITS: UnitSystem = "metric";

const GRAMS_PER_OUNCE = 28.349523125;
const GRAMS_PER_POUND = 453.59237;
const ML_PER_FL_OZ = 29.5735295625;
const KM_PER_MILE = 1.609344;
const FEET_PER_METER = 3.28084;
const CM_PER_INCH = 2.54;
const MM_PER_INCH = 25.4;

export function isUnitSystem(value: unknown): value is UnitSystem {
  return value === "metric" || value === "imperial";
}

/** What a viewer sees: guests always get metric; accounts get their setting. */
export function resolveUnits(signedIn: boolean, saved: UnitSystem | null | undefined): UnitSystem {
  return signedIn && isUnitSystem(saved) ? saved : DEFAULT_UNITS;
}

/**
 * Before the account setting existed, units were picked per browser. Returns
 * that choice when the account has none yet, so it can be saved once; null
 * when there's nothing to carry over.
 */
export function legacyUnitsToMigrate(saved: UnitSystem | null | undefined, legacy: string | null): UnitSystem | null {
  return saved == null && isUnitSystem(legacy) ? legacy : null;
}

export function metersToFeet(meters: number): number {
  return Math.round(meters * FEET_PER_METER);
}

export function celsiusToFahrenheit(celsius: number): number {
  return Math.round((celsius * 9) / 5 + 32);
}

function trim(value: number, decimals: number): string {
  return Number(value.toFixed(decimals)).toLocaleString("en-US", {
    maximumFractionDigits: decimals,
  });
}

/** "1,250 m" / "4,101 ft": elevations and elevation gain. */
export function formatElevation(meters: number, system: UnitSystem = DEFAULT_UNITS): string {
  return system === "metric"
    ? `${Math.round(meters).toLocaleString("en-US")} m`
    : `${metersToFeet(meters).toLocaleString("en-US")} ft`;
}

/** "12.4 km" / "7.7 mi"; whole numbers past 100 so long trails stay short. */
export function formatDistance(km: number, system: UnitSystem = DEFAULT_UNITS): string {
  const value = system === "metric" ? km : km / KM_PER_MILE;
  return `${trim(value, value >= 100 ? 0 : 1)} ${system === "metric" ? "km" : "mi"}`;
}

/** "100 km" / "62 mi": a distance rounded to a whole number, for goals. */
export function formatWholeDistance(km: number, system: UnitSystem = DEFAULT_UNITS): string {
  return `${Math.round(distanceValue(km, system)).toLocaleString("en-US")} ${distanceUnit(system)}`;
}

/** A distance in the reader's units, unrounded: 100 km → 62.14 (mi). */
export function distanceValue(km: number, system: UnitSystem = DEFAULT_UNITS): number {
  return system === "metric" ? km : km / KM_PER_MILE;
}

/** Back to km from a distance in "km" or "mi": 25 mi → 40.23. */
export function kmFromDistance(value: number, unit: "km" | "mi"): number {
  return unit === "km" ? value : value * KM_PER_MILE;
}

export function distanceUnit(system: UnitSystem = DEFAULT_UNITS): string {
  return system === "metric" ? "km" : "mi";
}

const ROUTE_DISTANCE_SUFFIX: Record<RouteType, string> = {
  out_and_back: "round trip",
  loop: "loop",
  point_to_point: "one way",
};

/** "8.6 km round trip", "12.4 km loop", "75.9 km one way". */
export function formatRouteDistance(km: number, routeType: RouteType, system: UnitSystem = DEFAULT_UNITS): string {
  return `${formatDistance(km, system)} ${ROUTE_DISTANCE_SUFFIX[routeType]}`;
}

/** Most catalogue trails still lack length and elevation data; null, zero or
 * nonsense values mean "unknown", so callers hide the field. */
function isKnownMeasure(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value) && value > 0;
}

/** Route distance when known, bare distance when the route type isn't, else null. */
export function formatTrailDistance(
  km: number | null | undefined,
  routeType: RouteType | null | undefined,
  system: UnitSystem = DEFAULT_UNITS,
): string | null {
  if (!isKnownMeasure(km)) return null;
  return routeType ? formatRouteDistance(km, routeType, system) : formatDistance(km, system);
}

/** Elevation or elevation gain when known, else null. */
export function formatTrailElevation(meters: number | null | undefined, system: UnitSystem = DEFAULT_UNITS): string | null {
  return isKnownMeasure(meters) ? formatElevation(meters, system) : null;
}

/** Bare degrees, for the low end of a range: "-4° / 12°C". */
export function formatDegrees(celsius: number, system: UnitSystem = DEFAULT_UNITS): string {
  return `${system === "metric" ? Math.round(celsius) : celsiusToFahrenheit(celsius)}°`;
}

/** "12°C" / "54°F". */
export function formatTemperature(celsius: number, system: UnitSystem = DEFAULT_UNITS): string {
  return `${formatDegrees(celsius, system)}${system === "metric" ? "C" : "F"}`;
}

const round1 = (value: number) => Number(value.toFixed(1)).toString();

/** "15 km/h" / "9 mph". */
export function formatWind(kmh: number, system: UnitSystem = DEFAULT_UNITS): string {
  return system === "metric" ? `${Math.round(kmh)} km/h` : `${Math.round(kmh / KM_PER_MILE)} mph`;
}

/** Rain: "2.4 mm" / "0.1 in"; tiny amounts read as a trace. */
export function formatPrecip(mm: number, system: UnitSystem = DEFAULT_UNITS): string {
  if (mm <= 0) return system === "metric" ? "0 mm" : "0 in";
  if (system === "metric") return mm < 0.1 ? "trace" : `${round1(mm)} mm`;
  const inches = mm / MM_PER_INCH;
  return inches < 0.01 ? "trace" : `${Number(inches.toFixed(2))} in`;
}

/** Snow: "3 cm" / "1.2 in"; amounts that round to zero read as a trace. */
export function formatSnow(cm: number, system: UnitSystem = DEFAULT_UNITS): string {
  const value = system === "metric" ? round1(cm) : round1(cm / CM_PER_INCH);
  if (Number(value) === 0) return cm > 0 ? "trace" : system === "metric" ? "0 cm" : "0 in";
  return `${value} ${system === "metric" ? "cm" : "in"}`;
}

/** Sizes: "23 cm" / "9.1 in". */
export function formatLength(cm: number, system: UnitSystem = DEFAULT_UNITS): string {
  return system === "metric" ? `${trim(cm, 1)} cm` : `${trim(cm / CM_PER_INCH, 1)} in`;
}

export function formatWeight(grams: number, system: UnitSystem = DEFAULT_UNITS): string {
  if (system === "metric") {
    return grams >= 1000 ? `${trim(grams / 1000, 2)} kg` : `${trim(grams, 0)} g`;
  }
  // Backpackers read weights as "2 lb 14 oz"; rounding to 0.1 oz happens
  // only here, for display.
  const tenthsOfOunce = Math.round((grams / GRAMS_PER_OUNCE) * 10);
  const pounds = Math.floor(tenthsOfOunce / 160);
  const ounces = (tenthsOfOunce - pounds * 160) / 10;
  if (pounds === 0) return `${trim(ounces, 1)} oz`;
  return ounces === 0 ? `${pounds} lb` : `${pounds} lb ${trim(ounces, 1)} oz`;
}

export function formatCapacity(ml: number, system: UnitSystem = DEFAULT_UNITS): string {
  // Pack volumes are quoted in litres in both systems.
  if (system === "metric" || ml >= 5000) {
    return ml >= 1000 ? `${trim(ml / 1000, 1)} L` : `${trim(ml, 0)} mL`;
  }
  return `${trim(ml / ML_PER_FL_OZ, 1)} fl oz`;
}

/* ---------- Weight entry ---------- */

const GRAMS_PER: Record<WeightUnit, number> = { g: 1, kg: 1000, oz: GRAMS_PER_OUNCE, lb: GRAMS_PER_POUND };

/** The units a weight can be typed in, for the reader's system only. */
export const WEIGHT_INPUT_UNITS: Record<UnitSystem, WeightUnit[]> = {
  metric: ["g", "kg"],
  imperial: ["oz", "lb"],
};

/** The unit to offer for a weight field: the one last used if it's in the reader's system. */
export function weightInputUnit(system: UnitSystem, previous?: WeightUnit | null): WeightUnit {
  return previous && WEIGHT_INPUT_UNITS[system].includes(previous) ? previous : WEIGHT_INPUT_UNITS[system][0];
}

/** Grams from a typed weight, to the 0.001 g the API stores; null if it isn't a number ≥ 0. */
export function gramsFromInput(value: string, unit: WeightUnit): number | null {
  const number = Number(value.trim());
  if (!value.trim() || !Number.isFinite(number) || number < 0) return null;
  return Number((number * GRAMS_PER[unit]).toFixed(3));
}

/** A stored weight as an editable number: 354.369 g reads back as 12.5 oz. */
export function gramsToInput(grams: number, unit: WeightUnit): string {
  return String(Number((grams / GRAMS_PER[unit]).toFixed(unit === "g" ? 1 : 3)));
}

/** Gear search "Under …" filters, labelled in the reader's system. */
export function weightFilters(system: UnitSystem): { label: string; grams: number | null }[] {
  const limits =
    system === "metric"
      ? [250, 500, 1000, 1500]
      : [0.5, 1, 2, 3].map((pounds) => Math.round(pounds * GRAMS_PER_POUND));
  return [{ label: "Any weight", grams: null }, ...limits.map((grams) => ({ label: `Under ${formatWeight(grams, system)}`, grams }))];
}

/** Water bottle size filters, labelled in the reader's system. */
export function bottleCapacityFilters(system: UnitSystem): { label: string; min?: number; max?: number }[] {
  // 1 L, or a US quart (32 fl oz).
  const split = system === "metric" ? 1000 : Math.round(32 * ML_PER_FL_OZ);
  return [
    { label: "Any size" },
    { label: `Up to ${formatCapacity(split, system)}`, max: split },
    { label: `Over ${formatCapacity(split, system)}`, min: split + 1 },
  ];
}

/* ---------- Free-text specs ---------- */

type Dimension = "length" | "mass";
const TEXT_UNITS: Record<string, { dimension: Dimension; system: UnitSystem; toBase: number }> = {
  // Lengths in centimetres, masses in grams.
  mm: { dimension: "length", system: "metric", toBase: 0.1 },
  cm: { dimension: "length", system: "metric", toBase: 1 },
  m: { dimension: "length", system: "metric", toBase: 100 },
  in: { dimension: "length", system: "imperial", toBase: CM_PER_INCH },
  inch: { dimension: "length", system: "imperial", toBase: CM_PER_INCH },
  inches: { dimension: "length", system: "imperial", toBase: CM_PER_INCH },
  ft: { dimension: "length", system: "imperial", toBase: 30.48 },
  g: { dimension: "mass", system: "metric", toBase: 1 },
  kg: { dimension: "mass", system: "metric", toBase: 1000 },
  oz: { dimension: "mass", system: "imperial", toBase: GRAMS_PER_OUNCE },
  lb: { dimension: "mass", system: "imperial", toBase: GRAMS_PER_POUND },
  lbs: { dimension: "mass", system: "imperial", toBase: GRAMS_PER_POUND },
};

/** The unit system of a measurement like "9 x 4.1 in", from its last unit. */
function textUnitSystem(text: string): UnitSystem | null {
  if (!/\d/.test(text)) return null;
  const units = text.toLowerCase().match(/[a-z]+/g) ?? [];
  for (let i = units.length - 1; i >= 0; i--) {
    const unit = TEXT_UNITS[units[i]];
    if (unit) return unit.system;
  }
  return null;
}

const NUMBER = String.raw`\d+(?:\.\d+)?`;
// "1.5 x 2.2 x 3.3 in", "16-19 in", "24+ in", "105 to 130 cm". Units
// followed by "/" (oz/sqyd) are compound and left alone.
const MEASURE = new RegExp(
  String.raw`(${NUMBER})((?:\s*(?:x|×|-|–|to)\s*${NUMBER})*)(\+?)\s*(mm|cm|m|inches|inch|in|ft|kg|g|oz|lbs|lb)\b(?![/.]?\d)(?!\s*/)`,
  "gi",
);
const POUNDS_OUNCES = new RegExp(String.raw`(\d+)\s*lbs?\s+(${NUMBER})\s*oz\b`, "gi");
// Words a pure measurement may carry: size labels and how it's measured.
const MEASUREMENT_WORDS =
  /\b(?:xxs|xs|s|m|l|xl|xxl|short|regular|medium|tall|long|small|large|wide|extra|diameter|by|and|high|deep|packed|length|width|height)\b/gi;

function convertMeasure(numbers: number[], unitKey: string, system: UnitSystem): string {
  const unit = TEXT_UNITS[unitKey.toLowerCase()];
  const base = numbers.map((value) => value * unit.toBase);
  const largest = Math.max(...base);
  if (unit.dimension === "mass") {
    if (system === "metric") {
      return largest >= 1000 ? `${base.map((g) => trim(g / 1000, 2)).join("|")} kg` : `${base.map((g) => trim(g, 0)).join("|")} g`;
    }
    return largest >= GRAMS_PER_POUND
      ? `${base.map((g) => trim(g / GRAMS_PER_POUND, 2)).join("|")} lb`
      : `${base.map((g) => trim(g / GRAMS_PER_OUNCE, 1)).join("|")} oz`;
  }
  if (system === "metric") {
    return largest >= 1000 ? `${base.map((cm) => trim(cm / 100, 1)).join("|")} m` : `${base.map((cm) => trim(cm, 1)).join("|")} cm`;
  }
  return largest >= 365.76 // 12 ft
    ? `${base.map((cm) => trim(cm / 30.48, 0)).join("|")} ft`
    : `${base.map((cm) => trim(cm / CM_PER_INCH, 1)).join("|")} in`;
}

/** Converts measurements in spec text that is only measurements ("16-19 in", "S 15-18 in, M 18-21 in"). */
function convertMeasurementText(text: string, system: UnitSystem): string {
  const leftover = text.replace(POUNDS_OUNCES, " ").replace(MEASURE, " ").replace(MEASUREMENT_WORDS, " ");
  // Anything else ("sold in 105-130 cm lengths", "18 oz polyester") is prose: left as written.
  if (/[a-z]/i.test(leftover) || !/\d/.test(text)) return text;
  return text
    .replace(POUNDS_OUNCES, (whole, pounds: string, ounces: string) =>
      system === "imperial" ? whole : formatWeight(Number(pounds) * GRAMS_PER_POUND + Number(ounces) * GRAMS_PER_OUNCE, system),
    )
    .replace(MEASURE, (whole, first: string, rest: string, plus: string, unitKey: string) => {
      if (TEXT_UNITS[unitKey.toLowerCase()].system === system) return whole;
      const separators = rest.match(/\s*(?:x|×|-|–|to)\s*/gi) ?? [];
      const numbers = [first, ...(rest.match(new RegExp(NUMBER, "g")) ?? [])].map(Number);
      const [joined, unit] = convertMeasure(numbers, unitKey, system).split(" ");
      const values = joined.split("|");
      return `${values.map((value, i) => (i === 0 ? value : `${separators[i - 1]}${value}`)).join("")}${plus} ${unit}`;
    });
}

/**
 * Spec text in the reader's system only. Dual-unit text such as
 * "9 x 4.1 in (23 x 10 cm)" keeps just the matching half ("23 x 10 cm" in
 * metric); text that is only measurements is converted; anything else is
 * prose and is left as written.
 */
export function specTextInSystem(text: string, system: UnitSystem): string {
  const match = /^(.+?)\s*\(([^()]+)\)$/.exec(text.trim());
  if (match) {
    const [, outer, inner] = match;
    const outerSystem = textUnitSystem(outer);
    const innerSystem = textUnitSystem(inner);
    if (outerSystem && innerSystem && outerSystem !== innerSystem) {
      return (outerSystem === system ? outer : inner).trim();
    }
  }
  return convertMeasurementText(text, system);
}

/** Format one API spec row (canonical units) for display. */
export function formatSpecValue(
  value: number | string | boolean,
  unit: string | null,
  system: UnitSystem = DEFAULT_UNITS,
): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return specTextInSystem(value, system);
  switch (unit) {
    case "g":
      return formatWeight(value, system);
    case "cm":
      return formatLength(value, system);
    case "m2":
      return system === "metric" ? `${trim(value, 2)} m²` : `${trim(value * 10.7639, 1)} sq ft`;
    case "c":
      return system === "metric" ? `${trim(value, 0)} °C` : `${celsiusToFahrenheit(value)} °F`;
    case "kg":
      return system === "metric" ? `${trim(value, 1)} kg` : `${trim(value * 2.20462, 0)} lb`;
    case "m":
      return system === "metric" ? `${trim(value, 0)} m` : `${metersToFeet(value)} ft`;
    case "l":
      return `${trim(value, 0)} L`;
    case "l/min":
      return system === "metric" ? `${trim(value, 2)} L/min` : `${trim((value * 1000) / ML_PER_FL_OZ, 1)} fl oz/min`;
    case "min":
      return `${trim(value, 1)} min`;
    case "h":
      return `${trim(value, 0)} h`;
    case "persons":
      return `${value} ${value === 1 ? "person" : "people"}`;
    case null:
      return trim(value, 2);
    default:
      return `${trim(value, 2)} ${unit}`;
  }
}

export const WEIGHT_BASIS_LABELS: Record<string, string> = {
  minimum: "minimum weight",
  trail: "trail weight",
  packaged: "packaged weight",
  average: "average weight",
  claimed: "manufacturer-listed weight",
};
