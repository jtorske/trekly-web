const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  trail_id: string;
  timezone: string | null;
  fetched_at: string;
  trailhead: ForecastPoint;
  /** The high point, when the catalogue knows it. */
  summit: ForecastPoint | null;
  source: "Open-Meteo";
}

/** Null when the trail has no forecast; throws when the service is down. */
export async function getTrailForecast(id: string, signal?: AbortSignal): Promise<TrailForecast | null> {
  const res = await fetch(`${API_BASE}/api/trails/${encodeURIComponent(id)}/forecast`, { signal });
  if (res.status === 404 || res.status === 422) return null;
  if (!res.ok) throw new Error("Forecast unavailable");
  return res.json();
}
