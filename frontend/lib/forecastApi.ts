/**
 * Five-day trail forecasts, fetched by the browser straight from Open-Meteo
 * (https://open-meteo.com, no key). Calling from the API server shared its
 * IP's rate limit with every other app on the host; each visitor now uses
 * their own.
 *
 * One request covers both points we forecast: the trailhead and, when we
 * know it, the high point. Open-Meteo corrects temperatures for the
 * elevation it's given, so both use the trail's coordinates with different
 * elevations. The trailhead follows the catalogue's own definition
 * (elevation gain = high point - trailhead); without it, Open-Meteo uses its
 * terrain model at the coordinates, which is where trails start.
 *
 * Results are kept in sessionStorage for an hour per trail. Data is CC BY
 * 4.0: the weather section credits Open-Meteo. Values are metric; lib/units
 * formats them.
 */

const FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
const FORECAST_DAYS = 5;
const CACHE_TTL_MS = 60 * 60 * 1000;
const CACHE_PREFIX = "trekly:forecast:";
const TIMEOUT_MS = 8000;
/** A high point this close to the trailhead adds nothing a hiker could use. */
export const MIN_SUMMIT_RISE_M = 150;
const DAILY = [
  "weather_code",
  "temperature_2m_max",
  "temperature_2m_min",
  "precipitation_probability_max",
  "precipitation_sum",
  "snowfall_sum",
  "wind_speed_10m_max",
  "sunrise",
  "sunset",
] as const;

export interface ForecastDay {
  /** YYYY-MM-DD at the trail. */
  date: string;
  /** WMO weather code. */
  weather_code: number | null;
  temp_max_c: number | null;
  temp_min_c: number | null;
  precip_probability_pct: number | null;
  precip_mm: number | null;
  snowfall_cm: number | null;
  wind_max_kmh: number | null;
  /** Local times at the trail, e.g. "2026-10-26T08:28". */
  sunrise: string | null;
  sunset: string | null;
}

export interface ForecastPoint {
  elevation_m: number | null;
  days: ForecastDay[];
}

export interface TrailForecast {
  timezone: string | null;
  fetched_at: string;
  trailhead: ForecastPoint;
  /** The high point, when the catalogue knows it. */
  summit: ForecastPoint | null;
}

/** What a forecast needs from a trail. */
export interface ForecastTrail {
  id: string;
  latitude: number | null;
  longitude: number | null;
  max_elevation_m: number | null;
  elevation_gain_m: number | null;
}

export interface ForecastPoints {
  latitude: number;
  longitude: number;
  /** Null: let Open-Meteo use its terrain model (the trailhead without data). */
  trailhead_m: number | null;
  summit_m: number | null;
}

/** Where to forecast, or null when the trail has no coordinates. */
export function forecastPoints(trail: ForecastTrail): ForecastPoints | null {
  if (trail.latitude == null || trail.longitude == null) return null;
  const high = trail.max_elevation_m;
  const trailhead = high != null && trail.elevation_gain_m != null ? high - trail.elevation_gain_m : null;
  const summit = high != null && (trailhead == null || high - trailhead >= MIN_SUMMIT_RISE_M) ? high : null;
  return { latitude: trail.latitude, longitude: trail.longitude, trailhead_m: trailhead, summit_m: summit };
}

export function forecastUrl(points: ForecastPoints): string {
  const params = new URLSearchParams({
    daily: DAILY.join(","),
    timezone: "auto",
    forecast_days: String(FORECAST_DAYS),
    wind_speed_unit: "kmh",
  });
  const lat = points.latitude.toFixed(4);
  const lon = points.longitude.toFixed(4);
  if (points.summit_m == null) {
    params.set("latitude", lat);
    params.set("longitude", lon);
    if (points.trailhead_m != null) params.set("elevation", String(points.trailhead_m));
  } else {
    // Two locations in one request. "nan" asks for the terrain model's
    // elevation at a point, so the trailhead keeps that fallback.
    params.set("latitude", `${lat},${lat}`);
    params.set("longitude", `${lon},${lon}`);
    params.set("elevation", `${points.trailhead_m ?? "nan"},${points.summit_m}`);
  }
  return `${FORECAST_URL}?${params}`;
}

/** The coordinates and elevations are part of the key, so a catalogue fix takes effect at once. */
export function cacheKey(trailId: string, points: ForecastPoints): string {
  return `${CACHE_PREFIX}${trailId}:${points.latitude.toFixed(4)}:${points.longitude.toFixed(4)}:${points.trailhead_m}:${points.summit_m}`;
}

export class ForecastUnavailable extends Error {}

type Json = Record<string, unknown>;
const isObject = (value: unknown): value is Json => typeof value === "object" && value !== null && !Array.isArray(value);

function days(location: Json): ForecastDay[] {
  const daily = location.daily;
  if (!isObject(daily) || !Array.isArray(daily.time)) throw new ForecastUnavailable("Open-Meteo response has no daily forecast");
  const count = daily.time.length;
  const columns = {} as Record<(typeof DAILY)[number], unknown[]>;
  for (const name of DAILY) {
    const values = daily[name];
    if (!Array.isArray(values) || values.length !== count) throw new ForecastUnavailable(`Open-Meteo response is missing ${name}`);
    columns[name] = values;
  }
  const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null);
  const str = (value: unknown) => (typeof value === "string" ? value : null);
  return (daily.time as unknown[]).map((date, i) => ({
    date: String(date),
    weather_code: num(columns.weather_code[i]),
    temp_max_c: num(columns.temperature_2m_max[i]),
    temp_min_c: num(columns.temperature_2m_min[i]),
    precip_probability_pct: num(columns.precipitation_probability_max[i]),
    precip_mm: num(columns.precipitation_sum[i]),
    snowfall_cm: num(columns.snowfall_sum[i]),
    wind_max_kmh: num(columns.wind_speed_10m_max[i]),
    sunrise: str(columns.sunrise[i]),
    sunset: str(columns.sunset[i]),
  }));
}

/** Open-Meteo's body (one location object, or a list of two) as a TrailForecast. */
export function parseForecast(body: unknown, points: ForecastPoints, fetchedAt: Date): TrailForecast {
  const locations = Array.isArray(body) ? body : [body];
  if (!locations.every(isObject)) throw new ForecastUnavailable("unexpected Open-Meteo response");
  const expected = points.summit_m == null ? 1 : 2;
  if (locations.length !== expected) throw new ForecastUnavailable(`expected ${expected} forecast locations, got ${locations.length}`);

  const point = (location: Json): ForecastPoint => ({
    elevation_m: typeof location.elevation === "number" ? Math.round(location.elevation) : null,
    days: days(location),
  });
  const trailhead = point(locations[0]);
  let summit = expected === 2 ? point(locations[1]) : null;
  // Without our own trailhead elevation, Open-Meteo's terrain model decides
  // it; drop a "summit" that turns out to be barely higher.
  if (
    summit &&
    trailhead.elevation_m != null &&
    summit.elevation_m != null &&
    summit.elevation_m - trailhead.elevation_m < MIN_SUMMIT_RISE_M
  ) {
    summit = null;
  }
  const timezone = typeof locations[0].timezone === "string" ? locations[0].timezone : null;
  return { timezone, fetched_at: fetchedAt.toISOString(), trailhead, summit };
}

/** A cached forecast younger than an hour, else null. */
export function readCached(storage: Pick<Storage, "getItem"> | null, key: string, now = Date.now()): TrailForecast | null {
  try {
    const cached = JSON.parse(storage?.getItem(key) ?? "null") as TrailForecast | null;
    if (!cached || !Array.isArray(cached.trailhead?.days)) return null;
    const age = now - Date.parse(cached.fetched_at);
    return age >= 0 && age < CACHE_TTL_MS ? cached : null;
  } catch {
    return null;
  }
}

/** The caller's signal plus a timeout, so a slow forecast never leaves a skeleton up. */
function withTimeout(signal?: AbortSignal): { signal: AbortSignal; done: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Forecast timed out", "TimeoutError")), TIMEOUT_MS);
  const forward = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", forward, { once: true });
  return {
    signal: controller.signal,
    done: () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", forward);
    },
  };
}

function session(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null; // blocked storage: fetch every time
  }
}

/**
 * The trail's forecast, from this tab's cache when it's under an hour old.
 * Null when the trail has no coordinates; throws when Open-Meteo fails, so
 * the page can hide the section.
 */
export async function getTrailForecast(trail: ForecastTrail, signal?: AbortSignal): Promise<TrailForecast | null> {
  const points = forecastPoints(trail);
  if (!points) return null;
  const key = cacheKey(trail.id, points);
  const storage = session();
  const cached = readCached(storage, key);
  if (cached) return cached;

  const request = withTimeout(signal);
  let body: unknown;
  try {
    const res = await fetch(forecastUrl(points), { signal: request.signal });
    if (!res.ok) throw new ForecastUnavailable(`Open-Meteo HTTP ${res.status}`);
    body = await res.json();
  } finally {
    request.done();
  }
  // Parse before caching, so a malformed response is never kept for an hour.
  const forecast = parseForecast(body, points, new Date());
  try {
    storage?.setItem(key, JSON.stringify(forecast));
  } catch {
    // Full or blocked storage: the forecast still shows, just uncached.
  }
  return forecast;
}
