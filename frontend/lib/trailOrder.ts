/**
 * Explore list ordering and titles. Pure functions so they can be
 * unit-tested; the API already returns trails most popular first.
 */

import type { Terrain } from "./terrain";

export type TrailSort = "popular" | "name" | "easiest" | "hardest" | "shortest" | "longest";

export const TRAIL_SORT_LABELS: Record<TrailSort, string> = {
  popular: "Most popular",
  name: "Name (A–Z)",
  easiest: "Easiest first",
  hardest: "Hardest first",
  shortest: "Shortest trip first",
  longest: "Longest trip first",
};

export function isTrailSort(value: string | null): value is TrailSort {
  return value !== null && Object.hasOwn(TRAIL_SORT_LABELS, value);
}

const TERRAIN_ORDER: Record<Terrain, number> = { easy: 0, moderate: 1, difficult: 2, extreme: 3 };

interface Sortable {
  name: string;
  terrain: Terrain;
  typical_duration_nights: number | null;
  distance_km: number | null;
}

const byName = (a: Sortable, b: Sortable) => a.name.localeCompare(b.name, "en", { sensitivity: "base" });

/** Trip length: nights, then distance. Unknown values sort last either way. */
function compareLength(a: Sortable, b: Sortable, direction: 1 | -1): number {
  for (const key of ["typical_duration_nights", "distance_km"] as const) {
    const x = a[key];
    const y = b[key];
    if (x == null && y == null) continue;
    if (x == null) return 1;
    if (y == null) return -1;
    if (x !== y) return (x - y) * direction;
  }
  return 0;
}

/** A sorted copy; ties keep the incoming (popularity) order. */
export function sortTrails<T extends Sortable>(trails: T[], sort: TrailSort): T[] {
  const compare: Record<TrailSort, ((a: T, b: T) => number) | null> = {
    popular: null,
    name: byName,
    easiest: (a, b) => TERRAIN_ORDER[a.terrain] - TERRAIN_ORDER[b.terrain],
    hardest: (a, b) => TERRAIN_ORDER[b.terrain] - TERRAIN_ORDER[a.terrain],
    shortest: (a, b) => compareLength(a, b, 1),
    longest: (a, b) => compareLength(a, b, -1),
  };
  const fn = compare[sort];
  return fn ? [...trails].sort(fn) : trails;
}

/** "Jasper National Park, AB" -> "Jasper National Park". */
export function parkName(region: string): string {
  return region.replace(/,\s*[A-Z]{2}$/, "").trim();
}

/**
 * Card titles by trail id. Trails that share a name ("Skyline Trail" in
 * Jasper and Cape Breton) get their park added so they can be told apart.
 */
export function trailTitles(trails: { id: string; name: string; region: string }[]): Map<string, string> {
  const counts = new Map<string, number>();
  for (const trail of trails) {
    const key = trail.name.trim().toLowerCase();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return new Map(
    trails.map((trail) => {
      const clash = (counts.get(trail.name.trim().toLowerCase()) ?? 0) > 1;
      const park = parkName(trail.region);
      return [trail.id, clash && park ? `${trail.name} (${park})` : trail.name];
    }),
  );
}
