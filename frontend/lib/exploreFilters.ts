/**
 * Explore's filters as URL state. Pure functions so links, the back button
 * and the page agree on one parse; the page reads the URL, never local copies.
 *
 * ?q=lake&trip=day&terrain=easy&province=AB&province=BC&park_type=national
 * &park=Banff+National+Park&near=1&within=50km&sort=nearest
 *
 * `near=1` only says "use my location": the position itself is never in the
 * URL. It is asked for again on load and kept in memory for the requests.
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

/** Filters counted on the Filters button: everything except search and sort. */
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
