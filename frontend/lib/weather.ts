import type { UnitSystem } from "./units";

/**
 * Display helpers for the trail forecast. The API's values are metric
 * (°C, km/h, mm, cm); these only format them.
 */

export type WeatherIcon = "clear" | "partly" | "cloudy" | "fog" | "drizzle" | "rain" | "freezing" | "snow" | "storm";

/** WMO weather interpretation codes, as Open-Meteo documents them. */
export function describeWeather(code: number | null): { label: string; icon: WeatherIcon } {
  switch (code) {
    case 0:
      return { label: "Clear", icon: "clear" };
    case 1:
      return { label: "Mainly clear", icon: "partly" };
    case 2:
      return { label: "Partly cloudy", icon: "partly" };
    case 3:
      return { label: "Overcast", icon: "cloudy" };
    case 45:
    case 48:
      return { label: "Fog", icon: "fog" };
    case 51:
    case 53:
    case 55:
      return { label: "Drizzle", icon: "drizzle" };
    case 56:
    case 57:
      return { label: "Freezing drizzle", icon: "freezing" };
    case 61:
      return { label: "Light rain", icon: "rain" };
    case 63:
      return { label: "Rain", icon: "rain" };
    case 65:
      return { label: "Heavy rain", icon: "rain" };
    case 66:
    case 67:
      return { label: "Freezing rain", icon: "freezing" };
    case 71:
      return { label: "Light snow", icon: "snow" };
    case 73:
      return { label: "Snow", icon: "snow" };
    case 75:
      return { label: "Heavy snow", icon: "snow" };
    case 77:
      return { label: "Snow grains", icon: "snow" };
    case 80:
    case 81:
      return { label: "Rain showers", icon: "rain" };
    case 82:
      return { label: "Violent rain showers", icon: "rain" };
    case 85:
    case 86:
      return { label: "Snow showers", icon: "snow" };
    case 95:
      return { label: "Thunderstorm", icon: "storm" };
    case 96:
    case 99:
      return { label: "Thunderstorm with hail", icon: "storm" };
    default:
      return { label: "Unknown", icon: "cloudy" };
  }
}

const round1 = (value: number) => Number(value.toFixed(1)).toString();

/** "15 km/h" / "9 mph". */
export function formatWind(kmh: number, system: UnitSystem): string {
  return system === "metric" ? `${Math.round(kmh)} km/h` : `${Math.round(kmh / 1.609344)} mph`;
}

/** "2.4 mm" / "0.1 in"; tiny amounts read as a trace. */
export function formatPrecip(mm: number, system: UnitSystem): string {
  if (mm <= 0) return system === "metric" ? "0 mm" : "0 in";
  if (system === "metric") return mm < 0.1 ? "trace" : `${round1(mm)} mm`;
  const inches = mm / 25.4;
  return inches < 0.01 ? "trace" : `${Number(inches.toFixed(2))} in`;
}

/** "3 cm" / "1.2 in" of snow; amounts that round to zero read as a trace. */
export function formatSnow(cm: number, system: UnitSystem): string {
  const value = system === "metric" ? round1(cm) : round1(cm / 2.54);
  if (Number(value) === 0) return cm > 0 ? "trace" : system === "metric" ? "0 cm" : "0 in";
  return `${value} ${system === "metric" ? "cm" : "in"}`;
}

/** "Today", "Tue", … for a YYYY-MM-DD at the trail, given today's date there. */
export function dayName(iso: string, today: string): string {
  if (iso === today) return "Today";
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-CA", { weekday: "short", timeZone: "UTC" });
}

/** "Oct 26". */
export function shortDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-CA", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** Today's date (YYYY-MM-DD) in `timeZone`, falling back to the device's. */
export function todayIn(timeZone: string | null, now = new Date()): string {
  const options = { year: "numeric", month: "2-digit", day: "2-digit" } as const;
  try {
    return new Intl.DateTimeFormat("en-CA", { ...options, timeZone: timeZone ?? undefined }).format(now);
  } catch {
    return new Intl.DateTimeFormat("en-CA", options).format(now);
  }
}

/** "2026-10-26T08:28" (local at the trail) → "8:28 a.m.". */
export function clockTime(local: string): string {
  const match = /T(\d{2}):(\d{2})/.exec(local);
  if (!match) return "";
  const hours = Number(match[1]);
  return `${hours % 12 || 12}:${match[2]} ${hours < 12 ? "a.m." : "p.m."}`;
}

/** Environment Canada's local forecast for the trail's coordinates. */
export function environmentCanadaUrl(latitude: number, longitude: number): string {
  return `https://weather.gc.ca/en/location/index.html?coords=${latitude.toFixed(3)},${longitude.toFixed(3)}`;
}

export const AVALANCHE_CANADA_URL = "https://avalanche.ca/map";
// Where Avalanche Canada publishes public avalanche forecasts.
const AVALANCHE_PROVINCES = new Set(["BC", "AB", "YT", "NL"]);

/** Avalanche Canada is worth linking October to May, in its forecast regions. */
export function showAvalancheLink(provinceCode: string | null, countryCode: string, date = new Date()): boolean {
  const month = date.getMonth() + 1;
  return countryCode === "CA" && AVALANCHE_PROVINCES.has(provinceCode ?? "") && (month >= 10 || month <= 5);
}
