import type { Terrain } from "@/lib/terrain";

export interface TrailSummary {
  id: string;
  name: string;
  region: string;
  terrain: Terrain;
}

export type RouteType = "out_and_back" | "loop" | "point_to_point";

/** An approved, credited trail photo (null on a trail means the topo fallback). */
export interface TrailPhoto {
  hero_url: string;
  thumb_url: string;
  width: number;
  height: number;
  photographer: string;
  /** Null for the site owner's own photos, credited by name only. */
  license: string | null;
  license_url: string | null;
  source_url: string | null;
  /** Where it was first published, e.g. "Flickr"; null for the owner's photos. */
  origin: string | null;
}

/** national = Parks Canada; provincial includes territorial parks, Quebec's
 * parcs nationaux and Kananaskis Country; regional = regional or municipal. */
export type ParkType = "national" | "provincial" | "regional" | "none";

/** Explore's park-type filter: "other" is regional parks and no park. */
export type ParkTypeFilter = "national" | "provincial" | "other";

export interface TrailListItem extends TrailSummary {
  country_code: string;
  province_code: string | null;
  /** Can be set with park_type "none" for a named place that isn't a park. */
  park_name: string | null;
  park_type: ParkType | null;
  typical_duration_nights: number | null;
  route_type: RouteType | null;
  /** Round trip for an out-and-back, the loop, or the full one-way length. */
  distance_km: number | null;
  elevation_gain_m: number | null;
  popularity_rank: number | null;
  /** Set once a trail leaves the catalogue; bookmarks to it still resolve. */
  retired_at: string | null;
  photo?: TrailPhoto | null;
}

/** "overnight" = backpacking trips (1+ typical nights), "day" = day hikes. */
export type TripType = "overnight" | "day";

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
  options: { terrain?: Terrain; trip?: TripType; limit?: number } = {},
): Promise<TrailListItem[]> {
  const params = new URLSearchParams({ q: query });
  if (options.terrain) params.set("terrain", options.terrain);
  if (options.trip) params.set("trip", options.trip);
  if (options.limit) params.set("limit", String(options.limit));

  const res = await fetch(`${API_BASE}/api/trails?${params}`, { signal });
  if (!res.ok) throw new Error("Failed to search trails");
  return res.json();
}

export interface TrailSearchRequest {
  q?: string;
  terrain?: Terrain;
  trip?: TripType;
  provinces?: string[];
  park_types?: ParkTypeFilter[];
  parks?: string[];
  /** Used for this request only; the API never stores or logs it. */
  near?: { lat: number; lng: number; radius_km?: number };
  limit?: number;
}

export interface TrailSearchItem extends TrailListItem {
  /** Straight-line km from `near`; null without it. */
  distance_away_km: number | null;
}

/** Every option, counted under all the other active filters. */
export interface TrailFacets {
  provinces: { code: string; count: number }[];
  park_types: { type: ParkTypeFilter; count: number }[];
  parks: { name: string; park_type: ParkType; province_codes: string[]; count: number }[];
}

export interface TrailSearchResult {
  trails: TrailSearchItem[];
  /** All matches, before `limit`. */
  total: number;
  facets: TrailFacets;
}

/**
 * Explore's search: trails, total and filter counts in one call. A POST so
 * the searcher's position travels in the body, never in a URL that could be
 * logged.
 */
export async function searchExplore(request: TrailSearchRequest, signal?: AbortSignal): Promise<TrailSearchResult> {
  const res = await fetch(`${API_BASE}/api/trails/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
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

export type CampgroundKind =
  | "zone"
  | "site"
  | "shelter"
  | "cabin"
  | "yurt"
  | "random_zone"
  | "horse_camp"
  | "backpacking_campground"
  | "trail_permit"
  | "other";

export interface TrailCampground {
  site_id: string;
  route_order: number;
  /** Groups individually booked pads at one place ("Fish Harbour"). */
  stop_name: string | null;
  notes: string | null;
  /** "likely" links are curated, not confirmed by the provider. */
  confidence: "exact" | "likely";
  /** The provider no longer lists this site. */
  retired: boolean;
  name: string;
  site_code: string | null;
  kind: CampgroundKind;
  area: string | null;
  park: { name: string; province_code: string | null } | null;
  reservable_capacity: number | null;
  max_capacity: number | null;
  max_group_size: number | null;
  provider: string;
}

/**
 * A Parks Canada booking form preset to a park and booking type. It never
 * opens a specific campground: trips are built as an itinerary there.
 */
export interface TrailBookingLink {
  label: string;
  url: string;
}

export interface TrailBooking {
  system: string;
  /** Null until the system is confirmed: show "Booked outside Trekly". */
  name: string | null;
  url: string | null;
  covers: "all" | "partial";
  confirmed: boolean;
  note: string | null;
}

export interface TrailCampgrounds {
  trail_id: string;
  trip_type: "overnight" | "day";
  /** A day hike with campgrounds on it ("Also doable as an overnight"). */
  overnight_option: boolean;
  route_order_approximate: boolean;
  booking: TrailBooking[];
  booking_links: TrailBookingLink[];
  campgrounds: TrailCampground[];
}

export async function getTrailCampgrounds(
  id: string,
  signal?: AbortSignal,
): Promise<TrailCampgrounds> {
  const res = await fetch(
    `${API_BASE}/api/trails/${encodeURIComponent(id)}/campgrounds`,
    { signal },
  );
  if (!res.ok) throw new Error("Failed to load campgrounds");
  return res.json();
}
