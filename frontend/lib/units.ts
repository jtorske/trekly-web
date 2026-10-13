/**
 * Display conversions. Canonical values from the API are grams, millilitres,
 * centimetres and °C; these functions only format them — they never round
 * the stored value.
 */

export type UnitSystem = "imperial" | "metric";

const GRAMS_PER_OUNCE = 28.349523125;
const ML_PER_FL_OZ = 29.5735295625;

export function metersToFeet(meters: number): number {
  return Math.round(meters * 3.28084);
}

export function celsiusToFahrenheit(celsius: number): number {
  return Math.round((celsius * 9) / 5 + 32);
}

function trim(value: number, decimals: number): string {
  return Number(value.toFixed(decimals)).toLocaleString("en-US", {
    maximumFractionDigits: decimals,
  });
}

export function formatWeight(grams: number, system: UnitSystem = "imperial"): string {
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

export function formatCapacity(ml: number, system: UnitSystem = "imperial"): string {
  if (system === "metric" || ml >= 5000) {
    return ml >= 1000 ? `${trim(ml / 1000, 1)} L` : `${trim(ml, 0)} mL`;
  }
  return `${trim(ml / ML_PER_FL_OZ, 1)} fl oz`;
}

/** Format one API spec row (canonical units) for display. */
export function formatSpecValue(
  value: number | string | boolean,
  unit: string | null,
  system: UnitSystem = "imperial",
): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  switch (unit) {
    case "g":
      return formatWeight(value, system);
    case "cm":
      return system === "metric" ? `${trim(value, 1)} cm` : `${trim(value / 2.54, 1)} in`;
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
      return `${trim(value, 2)} L/min`;
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
