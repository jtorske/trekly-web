import type { TrailListItem } from "./trailsApi";

/**
 * "Which of these have you hiked?": the order trails are offered in, and
 * search within them. Trails in the hiker's home province come first, then
 * ones in their favourite regions (onboarding's "Which places are on your
 * radar?"), then everything else; within each, most popular first.
 */
export interface PickerPreferences {
  homeProvince?: string | null;
  /** Region or park names, matched loosely against a trail's region and park. */
  favouriteRegions?: string[];
}

const fold = (text: string) =>
  text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

function tier(trail: TrailListItem, prefs: PickerPreferences, favourites: string[]): number {
  if (prefs.homeProvince && trail.province_code === prefs.homeProvince) return 0;
  const place = fold(`${trail.region} ${trail.park_name ?? ""}`);
  if (favourites.some((favourite) => place.includes(favourite))) return 1;
  return 2;
}

export function orderForPicker(trails: TrailListItem[], prefs: PickerPreferences = {}): TrailListItem[] {
  const favourites = (prefs.favouriteRegions ?? []).map(fold).filter(Boolean);
  const rank = (trail: TrailListItem) => trail.popularity_rank ?? Number.MAX_SAFE_INTEGER;
  return trails
    .filter((trail) => !trail.retired_at)
    .map((trail) => ({ trail, tier: tier(trail, prefs, favourites) }))
    .sort((a, b) => a.tier - b.tier || rank(a.trail) - rank(b.trail) || a.trail.name.localeCompare(b.trail.name))
    .map(({ trail }) => trail);
}

/** Trails whose name, park or region has every word of the query. */
export function searchPicker(trails: TrailListItem[], query: string): TrailListItem[] {
  const words = fold(query).split(" ").filter(Boolean);
  if (words.length === 0) return trails;
  return trails.filter((trail) => {
    const text = fold(`${trail.name} ${trail.park_name ?? ""} ${trail.region}`);
    return words.every((word) => text.includes(word));
  });
}

/** Adds trails from a server search that aren't listed yet, after the local ones. */
export function mergeTrails(local: TrailListItem[], extra: TrailListItem[]): TrailListItem[] {
  const seen = new Set(local.map((trail) => trail.id));
  return [...local, ...extra.filter((trail) => !trail.retired_at && !seen.has(trail.id))];
}

// ------------------------------------------------- grouping, sorting, filters

export type PickerSort = "park" | "nearest" | "popular" | "az";

export const PICKER_SORTS: { value: PickerSort; label: string }[] = [
  { value: "park", label: "By park" },
  { value: "nearest", label: "Nearest to me" },
  { value: "popular", label: "Most popular" },
  { value: "az", label: "A–Z" },
];

export interface PickerGroup {
  /** The park, or the region for a trail outside one. */
  key: string;
  title: string;
  province: string | null;
  trails: TrailListItem[];
}

const popularity = (trail: TrailListItem) => trail.popularity_rank ?? Number.MAX_SAFE_INTEGER;
const byPopularity = (a: TrailListItem, b: TrailListItem) => popularity(a) - popularity(b) || a.name.localeCompare(b.name);
const placeOf = (trail: TrailListItem) => trail.park_name ?? trail.region;

/**
 * "By park": trails in collapsible groups, one per park (or region), in the
 * order people are likeliest to find their own hikes: their home province's
 * parks, then the parks on their radar, then everything else by province
 * (then park) A–Z. Within each group, most popular first; the groups within a
 * band go by their most popular trail.
 */
export function groupForPicker(
  trails: TrailListItem[],
  prefs: PickerPreferences = {},
  provinceName: (code: string) => string = (code) => code,
): PickerGroup[] {
  const favourites = (prefs.favouriteRegions ?? []).map(fold).filter(Boolean);
  const groups = new Map<string, PickerGroup>();
  for (const trail of trails) {
    if (trail.retired_at) continue;
    const title = placeOf(trail);
    const key = `${trail.province_code ?? ""}|${title}`;
    let group = groups.get(key);
    if (!group) {
      group = { key, title, province: trail.province_code, trails: [] };
      groups.set(key, group);
    }
    group.trails.push(trail);
  }
  const band = (group: PickerGroup) => {
    if (prefs.homeProvince && group.province === prefs.homeProvince) return 0;
    const place = fold(group.title);
    return favourites.some((favourite) => place.includes(favourite)) ? 1 : 2;
  };
  const list = [...groups.values()];
  for (const group of list) group.trails.sort(byPopularity);
  const best = (group: PickerGroup) => popularity(group.trails[0]);
  const provinceLabel = (group: PickerGroup) => (group.province ? provinceName(group.province) : "~");
  return list.sort((a, b) => {
    const bands = band(a) - band(b);
    if (bands) return bands;
    if (band(a) < 2) return best(a) - best(b) || a.title.localeCompare(b.title);
    return provinceLabel(a).localeCompare(provinceLabel(b)) || a.title.localeCompare(b.title);
  });
}

/** Great-circle distance in km. */
export function distanceKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
}

/**
 * A flat list in one of the non-park orders. "nearest" needs `here` (the
 * browser's location, used only for this ordering and never stored); without
 * it, or for trails with no trailhead, it falls back to popularity.
 */
export function sortForPicker(
  trails: TrailListItem[],
  sort: Exclude<PickerSort, "park">,
  here: { lat: number; lon: number } | null = null,
): TrailListItem[] {
  const live = trails.filter((trail) => !trail.retired_at);
  if (sort === "az") {
    return live.sort((a, b) => a.name.localeCompare(b.name) || placeOf(a).localeCompare(placeOf(b)));
  }
  if (sort === "nearest" && here) {
    const away = (trail: TrailListItem) =>
      trail.latitude != null && trail.longitude != null
        ? distanceKm(here, { lat: trail.latitude, lon: trail.longitude })
        : Number.POSITIVE_INFINITY;
    return live
      .map((trail) => ({ trail, km: away(trail) }))
      .sort((a, b) => a.km - b.km || byPopularity(a.trail, b.trail))
      .map(({ trail }) => trail);
  }
  return live.sort(byPopularity);
}

/** Only trails in the chosen provinces; no choice means all of them. */
export function filterProvinces(trails: TrailListItem[], provinces: ReadonlySet<string>): TrailListItem[] {
  if (provinces.size === 0) return trails;
  return trails.filter((trail) => trail.province_code !== null && provinces.has(trail.province_code));
}

/** The provinces the trails are in, for the chips, most trails first. */
export function pickerProvinces(trails: TrailListItem[]): string[] {
  const counts = new Map<string, number>();
  for (const trail of trails) {
    if (trail.retired_at || !trail.province_code) continue;
    counts.set(trail.province_code, (counts.get(trail.province_code) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([code]) => code);
}

/**
 * Trail names that more than one trail shares (two Skyline Trails), so their
 * cards always say where they are, even inside a park's group.
 */
export function sharedNames(trails: TrailListItem[]): Set<string> {
  const seen = new Map<string, number>();
  for (const trail of trails) seen.set(fold(trail.name), (seen.get(fold(trail.name)) ?? 0) + 1);
  return new Set([...seen.entries()].filter(([, count]) => count > 1).map(([name]) => name));
}

/** Whether another trail has this one's name (see sharedNames). */
export function hasSharedName(trail: TrailListItem, shared: ReadonlySet<string>): boolean {
  return shared.has(fold(trail.name));
}

/** The place line on a trail's card: always the park, plus the province when two same-named trails share a park name. */
export function placeLine(trail: TrailListItem, shared: ReadonlySet<string>, all: TrailListItem[]): string {
  const place = placeOf(trail);
  if (!shared.has(fold(trail.name)) || !trail.province_code) return place;
  const twin = all.some((other) => other.id !== trail.id && fold(other.name) === fold(trail.name) && placeOf(other) === place);
  return twin ? `${place}, ${trail.province_code}` : place;
}

/** "Banff National Park · 23 trails". */
export function groupHeading(group: PickerGroup): string {
  return `${group.title} · ${group.trails.length} ${group.trails.length === 1 ? "trail" : "trails"}`;
}

/** "6 trails picked". */
export function pickedCount(count: number): string {
  return count === 0 ? "Nothing picked yet" : `${count} ${count === 1 ? "trail" : "trails"} picked`;
}
