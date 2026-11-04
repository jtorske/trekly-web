/**
 * Explore's filters as URL state. Pure functions so links, the back button
 * and the page agree on one parse; the page reads the URL, never local copies.
 *
 * ?q=lake&trip=day&terrain=easy&province=AB&province=BC&park_type=national
 * &park=Banff+National+Park&near=1&within=50km&sort=nearest
 *
 * `near=1` only says "use my location": the position itself is never in the
 * URL. It is asked for again on load and kept in memory for the requests.
 *
 * The map's position (`map=lat,lng,zoom`), the phone's Map/List choice
 * (`view=map`) and "Search as I move the map" turned off (`follow=0`) are
 * view state, not filters: they ride along unchanged when a filter changes
 * (keepViewParams). The list follows the map's visible area, which lives in
 * memory: it comes from the map itself, never from the URL.
 */

import { TERRAIN_LABELS, type Terrain } from "./terrain.ts";
import { isTrailSort, type TrailSort } from "./trailOrder.ts";
import type { ParkTypeFilter, TripType } from "./trailsApi";
import { kmFromDistance } from "./units.ts";

export type DistanceUnit = "km" | "mi";

export interface Within {
  value: number;
  unit: DistanceUnit;
}

/** A map view's edges, in degrees. West > east crosses the antimeridian. */
export interface Bounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface ExploreFilters {
  q: string;
  trip?: TripType;
  terrain?: Terrain;
  provinces: string[];
  parkTypes: ParkTypeFilter[];
  parks: string[];
  near: boolean;
  /** Only with `near`. */
  within?: Within;
  sort: TrailSort;
}

export const EMPTY_FILTERS: ExploreFilters = { q: "", provinces: [], parkTypes: [], parks: [], near: false, sort: "popular" };

/** West to east, then the territories: the order the chips show in. */
export const PROVINCE_NAMES: Record<string, string> = {
  BC: "British Columbia",
  AB: "Alberta",
  SK: "Saskatchewan",
  MB: "Manitoba",
  ON: "Ontario",
  QC: "Quebec",
  NB: "New Brunswick",
  NS: "Nova Scotia",
  PE: "Prince Edward Island",
  NL: "Newfoundland and Labrador",
  YT: "Yukon",
  NT: "Northwest Territories",
  NU: "Nunavut",
};
const PROVINCE_ORDER = Object.keys(PROVINCE_NAMES);

export function provinceOrder(a: string, b: string): number {
  const rank = (code: string) => (PROVINCE_ORDER.includes(code) ? PROVINCE_ORDER.indexOf(code) : PROVINCE_ORDER.length);
  return rank(a) - rank(b) || a.localeCompare(b);
}

export const TRIP_LABELS: Record<TripType, string> = {
  overnight: "Backpacking",
  day: "Day hikes",
};

export const PARK_TYPE_LABELS: Record<ParkTypeFilter, string> = {
  national: "National parks",
  provincial: "Provincial & territorial parks",
  other: "Other",
};

/** The distance options, in the reader's units. */
export const WITHIN_OPTIONS = [25, 50, 100, 250];

export function withinKm(within: Within): number {
  return kmFromDistance(within.value, within.unit);
}

export function withinLabel(within: Within): string {
  return `Within ${within.value} ${within.unit}`;
}

function parseWithin(value: string | null): Within | undefined {
  const match = value?.match(/^(\d+)(km|mi)$/);
  if (!match) return undefined;
  const amount = Number(match[1]);
  return WITHIN_OPTIONS.includes(amount) ? { value: amount, unit: match[2] as DistanceUnit } : undefined;
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

const pick = <T extends string>(options: readonly T[], value: string | null): T | undefined =>
  value !== null && (options as readonly string[]).includes(value) ? (value as T) : undefined;

/** 4 places is about 10 m: plenty for a map view, and short URLs. */
const round = (value: number, places: number) => Number(value.toFixed(places));

export function parseExploreParams(params: URLSearchParams): ExploreFilters {
  const near = params.get("near") === "1";
  const sort = params.get("sort");
  return {
    q: params.get("q")?.trim() ?? "",
    trip: pick(Object.keys(TRIP_LABELS) as TripType[], params.get("trip")),
    terrain: pick(Object.keys(TERRAIN_LABELS) as Terrain[], params.get("terrain")),
    provinces: unique(params.getAll("province").map((p) => p.trim().toUpperCase()).filter((p) => /^[A-Z]{2}$/.test(p))),
    parkTypes: unique(
      params.getAll("park_type").flatMap((t) => pick(Object.keys(PARK_TYPE_LABELS) as ParkTypeFilter[], t) ?? []),
    ),
    parks: unique(params.getAll("park").map((p) => p.trim()).filter(Boolean)),
    near,
    within: near ? parseWithin(params.get("within")) : undefined,
    // "Nearest" needs a location to sort by.
    sort: isTrailSort(sort) && (sort !== "nearest" || near) ? sort : "popular",
  };
}

/** The query string for `filters`, in a fixed order; "" when nothing is set. */
export function exploreSearch(filters: ExploreFilters): string {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.trip) params.set("trip", filters.trip);
  if (filters.terrain) params.set("terrain", filters.terrain);
  for (const code of filters.provinces) params.append("province", code);
  for (const type of filters.parkTypes) params.append("park_type", type);
  for (const park of filters.parks) params.append("park", park);
  if (filters.near) {
    params.set("near", "1");
    if (filters.within) params.set("within", `${filters.within.value}${filters.within.unit}`);
  }
  if (filters.sort !== "popular" && (filters.sort !== "nearest" || filters.near)) params.set("sort", filters.sort);
  return params.toString();
}

export function exploreHref(filters: Partial<ExploreFilters>): string {
  const search = exploreSearch({ ...EMPTY_FILTERS, ...filters });
  return search ? `/trail-list?${search}` : "/trail-list";
}

/** Filters counted on the Filters button: everything in the panel (not the
 * search box or the sort). */
export function activeFilterCount(filters: ExploreFilters): number {
  return (
    (filters.trip ? 1 : 0) +
    (filters.terrain ? 1 : 0) +
    filters.provinces.length +
    filters.parkTypes.length +
    filters.parks.length +
    (filters.near ? 1 : 0)
  );
}

/** Everything cleared except the search box. */
export function clearFilters(filters: ExploreFilters): ExploreFilters {
  return { ...EMPTY_FILTERS, q: filters.q, sort: filters.sort === "nearest" ? "popular" : filters.sort };
}

export function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}

/** Turning location off also drops the distance and the "Nearest" sort. */
export function withoutNear(filters: ExploreFilters): ExploreFilters {
  return { ...filters, near: false, within: undefined, sort: filters.sort === "nearest" ? "popular" : filters.sort };
}

/**
 * Province chips changed: drop picked parks that are no longer in any picked
 * province, so the park list (narrowed to those provinces) never hides a
 * selection that silently empties the results.
 */
export function withProvinces(
  filters: ExploreFilters,
  provinces: string[],
  parkProvinces: Map<string, string[]>,
): ExploreFilters {
  const parks = provinces.length
    ? filters.parks.filter((park) => {
        const codes = parkProvinces.get(park);
        return !codes || codes.some((code) => provinces.includes(code));
      })
    : filters.parks;
  return { ...filters, provinces, parks };
}

/** Where the map is looking. */
export interface MapView {
  lat: number;
  lng: number;
  zoom: number;
}

export function parseMapView(params: URLSearchParams): MapView | null {
  const parts = params.get("map")?.split(",").map(Number);
  if (!parts || parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return null;
  const [lat, lng, zoom] = parts;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180 || zoom < 0 || zoom > 22) return null;
  return { lat, lng, zoom };
}

export function formatMapView(view: MapView): string {
  return `${round(view.lat, 4)},${round(view.lng, 4)},${round(view.zoom, 2)}`;
}

/**
 * The part of Canada the trails sit in. A map view that takes all of it in
 * is "all of Canada": the list shows every result, not just this area.
 * A couple of degrees' slack, so a view fitted to Canada still counts.
 */
const CANADA_VIEW: Bounds = { west: -139, south: 43.5, east: -54.5, north: 60 };

/** Into -180..180, keeping 180 itself (the east edge of a view that ends there). */
function wrapLng(lng: number): number {
  const wrapped = ((((lng + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 && lng > 0 ? 180 : wrapped;
}

/**
 * What the list searches for a map view's edges (as the map reports them:
 * longitudes can run past ±180 when the world repeats). Undefined when the
 * view takes in all of Canada or the whole world: then nothing is filtered
 * by area. Rounded to about 10 m, so tiny nudges don't refetch.
 */
export function searchAreaFor(view: Bounds): Bounds | undefined {
  if (view.east - view.west >= 360) return undefined;
  const south = Math.max(-90, view.south);
  const north = Math.min(90, view.north);
  if (
    view.west <= CANADA_VIEW.west &&
    view.east >= CANADA_VIEW.east &&
    south <= CANADA_VIEW.south &&
    north >= CANADA_VIEW.north
  ) {
    return undefined;
  }
  return {
    west: round(wrapLng(view.west), 4),
    south: round(south, 4),
    east: round(wrapLng(view.east), 4),
    north: round(north, 4),
  };
}

/** Below the split layout, Explore shows the list or the map; "list" by default. */
export type ExploreView = "list" | "map";

export function parseExploreView(params: URLSearchParams): ExploreView {
  return params.get("view") === "map" ? "map" : "list";
}

/** "Search as I move the map": on unless the URL turned it off. */
export function parseFollowMap(params: URLSearchParams): boolean {
  return params.get("follow") !== "0";
}

type ViewParam = "map" | "view" | "follow";
const VIEW_PARAMS: ViewParam[] = ["map", "view", "follow"];

/** `search` (filters only) with the view params from `current` kept. */
export function keepViewParams(search: string, current: URLSearchParams): string {
  const params = new URLSearchParams(search);
  for (const key of VIEW_PARAMS) {
    const value = current.get(key);
    if (value !== null) params.set(key, value);
  }
  return params.toString();
}

/** `current` with one view param set, or removed with null. */
export function withViewParam(current: URLSearchParams, key: ViewParam, value: string | null): string {
  const params = new URLSearchParams(current);
  if (value === null) params.delete(key);
  else params.set(key, value);
  return params.toString();
}

/** The parks among the quick chips under the search bar, with their chip labels. */
export const QUICK_PARKS: { park: string; label: string }[] = [
  { park: "Banff National Park", label: "Banff" },
  { park: "Jasper National Park", label: "Jasper" },
  { park: "Kananaskis Country", label: "Kananaskis" },
];

/**
 * The quick park chips: the signed-in person's favourite regions first (from
 * /welcome or Settings → Trail preferences), then the usual ones not already
 * there.
 */
export function quickParks(favourites: { park: string; label: string }[]): { park: string; label: string }[] {
  const seen = new Set(favourites.map((f) => f.park));
  return [...favourites, ...QUICK_PARKS.filter((q) => !seen.has(q.park))];
}

/**
 * Favourite parks start picked only on a bare /trail-list (no filters, no map
 * position in the URL): a shared link or the back button keeps what it says.
 */
export function shouldPreselectFavourites(search: string, favouriteCount: number): boolean {
  return favouriteCount > 0 && new URLSearchParams(search).toString() === "";
}

/** Day hikes and Backpacking chips: picking one replaces the other, picking it again clears it. */
export function toggleTrip(filters: ExploreFilters, trip: TripType): ExploreFilters {
  return { ...filters, trip: filters.trip === trip ? undefined : trip };
}
