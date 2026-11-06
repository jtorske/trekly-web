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
