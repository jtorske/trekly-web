import type { Terrain } from "@/lib/terrain";

export interface TrailSummary {
  id: string;
  name: string;
  region: string;
  terrain: Terrain;
}

export interface TrailListItem extends TrailSummary {
  country_code: string;
  province_code: string | null;
  typical_duration_nights: number | null;
  elevation_gain_m: number | null;
  popularity_rank: number | null;
  /** Set once a trail leaves the catalogue; bookmarks to it still resolve. */
  retired_at: string | null;
}

export type Season = "spring" | "summer" | "fall" | "winter";

export interface SeasonalCondition {
  season: Season;
  avg_low_c: number;
  avg_high_c: number;
  precip_likelihood: "low" | "moderate" | "high" | null;
  high_wind: boolean | null;
  notes: string | null;
}

export interface TrailDetail extends TrailListItem {
  max_elevation_m: number | null;
  latitude: number | null;
  longitude: number | null;
  climate_zone: string | null;
  description: string | null;
  seasonal_conditions: SeasonalCondition[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function searchTrails(
  query: string,
  signal?: AbortSignal,
  options: { terrain?: Terrain; limit?: number } = {},
): Promise<TrailListItem[]> {
  const params = new URLSearchParams({ q: query });
  if (options.terrain) params.set("terrain", options.terrain);
  if (options.limit) params.set("limit", String(options.limit));

  const res = await fetch(`${API_BASE}/api/trails?${params}`, { signal });
  if (!res.ok) throw new Error("Failed to search trails");
  return res.json();
}

export async function getTrail(
  id: string,
  signal?: AbortSignal,
): Promise<TrailDetail | null> {
  const res = await fetch(`${API_BASE}/api/trails/${encodeURIComponent(id)}`, {
    signal,
  });
  // 422 means the id isn't a valid UUID — treat it the same as a missing trail.
  if (res.status === 404 || res.status === 422) return null;
  if (!res.ok) throw new Error("Failed to load trail");
  return res.json();
}
