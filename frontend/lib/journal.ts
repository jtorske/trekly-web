import type { HikeLog } from "./hikeLogsApi";
import type { TrailListItem } from "./trailsApi";
import { distanceValue, formatDistance, type UnitSystem } from "./units.ts";

/**
 * The Trail Journal's layout: which trails go on which spread, in which
 * order, and the cover's and milestones' numbers. Pure, so the book renders
 * the same for a guest (no logs) and a user, and so it can be tested.
 *
 * A region with at least PARK_SPREAD_MIN trails (Banff, Kananaskis …) gets
 * its own spread; the rest are gathered by province ("More of Alberta"), so
 * 60 one-trail regions don't become 60 near-empty spreads.
 */

export const PARK_SPREAD_MIN = 3;

// West to east, then the territories' neighbours; other countries follow.
const PROVINCE_ORDER = ["YT", "NT", "NU", "BC", "AB", "SK", "MB", "ON", "QC", "NB", "NS", "PE", "NL"];
const PROVINCE_NAMES: Record<string, string> = {
  YT: "Yukon",
  NT: "Northwest Territories",
  NU: "Nunavut",
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
};
const COUNTRY_NAMES: Record<string, string> = { US: "United States" };

// Earthy inks that read as badge fills on cream and on the dark page, each
// with cream text at >= 4.5:1.
export const BADGE_COLOURS = [
  "#5a6b2f", // olive
  "#8a4a1c", // rust
  "#2f5d62", // glacier teal
  "#6b3f5a", // fireweed
  "#3d4f7a", // lake blue
  "#7a5a1e", // larch gold
  "#4a5e43", // spruce
  "#8b3a3a", // red rock
  "#4b4f58", // granite
  "#5c4a32", // bark
];

export interface JournalGroup {
  key: string;
  title: string;
  subtitle: string;
  colour: string;
  trails: TrailListItem[];
}

/**
 * One stop in the book, opened from the contents: a two-page spread on
 * desktop, one page (or two, if it doesn't fit) on a phone.
 */
export type JournalSection =
  | { kind: "contents"; slug: null; title: string }
  | { kind: "group"; slug: string; title: string; group: JournalGroup }
  | { kind: "milestones"; slug: "milestones"; title: string };

export interface Milestone {
  id: "first-hike" | "first-overnight" | "five-parks" | "hundred-km";
  title: string;
  detail: string;
  earned: boolean;
  /** 0–1 towards earning it. */
  progress: number;
}

export interface Journal {
  groups: JournalGroup[];
  /** Contents first, then each group, then milestones. */
  sections: JournalSection[];
  hiked: number;
  total: number;
  milestones: Milestone[];
}

/** "Banff National Park, AB" → "Banff National Park". */
export function regionTitle(region: string): string {
  return region.replace(/,\s*[A-Z]{2}$/, "").trim();
}

export function placeName(trail: Pick<TrailListItem, "country_code" | "province_code">): string {
  if (trail.country_code === "CA" && trail.province_code) {
    return PROVINCE_NAMES[trail.province_code] ?? trail.province_code;
  }
  return COUNTRY_NAMES[trail.country_code] ?? trail.country_code;
}

function placeKey(trail: TrailListItem): string {
  return trail.country_code === "CA" ? `CA-${trail.province_code ?? "?"}` : trail.country_code;
}

function placeRank(key: string): number {
  const index = PROVINCE_ORDER.indexOf(key.replace(/^CA-/, ""));
  if (key.startsWith("CA-")) return index === -1 ? PROVINCE_ORDER.length : index;
  return PROVINCE_ORDER.length + 1;
}

/** A stable colour per group, so a park keeps its colour as the catalogue changes. */
export function groupColour(key: string): string {
  let hash = 0;
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return BADGE_COLOURS[hash % BADGE_COLOURS.length];
}

const byRank = (a: TrailListItem, b: TrailListItem) =>
  (a.popularity_rank ?? Number.MAX_SAFE_INTEGER) - (b.popularity_rank ?? Number.MAX_SAFE_INTEGER) ||
  a.name.localeCompare(b.name);

export function groupTrails(trails: TrailListItem[]): JournalGroup[] {
  const regionCounts = new Map<string, number>();
  for (const trail of trails) regionCounts.set(trail.region, (regionCounts.get(trail.region) ?? 0) + 1);

  const groups = new Map<string, JournalGroup & { place: string; isPark: boolean }>();
  for (const trail of trails) {
    const place = placeKey(trail);
    const isPark = (regionCounts.get(trail.region) ?? 0) >= PARK_SPREAD_MIN;
    const key = isPark ? `region:${trail.region}` : `place:${place}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        title: isPark ? regionTitle(trail.region) : placeName(trail),
        subtitle: isPark ? placeName(trail) : "",
        colour: groupColour(key),
        trails: [],
        place,
        isPark,
      };
      groups.set(key, group);
    }
    group.trails.push(trail);
  }

  const all = [...groups.values()];
  for (const group of all) {
    group.trails.sort(byRank);
    if (!group.isPark) {
      const hasParks = all.some((other) => other.isPark && other.place === group.place);
      const regions = new Set(group.trails.map((trail) => regionTitle(trail.region)));
      group.subtitle = `${regions.size} ${regions.size === 1 ? "place" : "places"}`;
      if (hasParks) group.title = `More of ${group.title}`;
    }
  }
  // By province west to east; parks (largest first) before the province's "More of".
  all.sort(
    (a, b) =>
      placeRank(a.place) - placeRank(b.place) ||
      a.place.localeCompare(b.place) ||
      Number(b.isPark) - Number(a.isPark) ||
      b.trails.length - a.trails.length ||
      a.title.localeCompare(b.title),
  );
  return all.map(({ key, title, subtitle, colour, trails: groupTrails }) => ({ key, title, subtitle, colour, trails: groupTrails }));
}

export function computeMilestones(logs: HikeLog[], units: UnitSystem = "metric"): Milestone[] {
  const overnight = logs.some((log) => (log.trail.typical_duration_nights ?? 0) >= 1);
  const parks = new Set(logs.map((log) => log.trail.region)).size;
  // Only trails with a known distance count towards the total.
  const km = logs.reduce((sum, log) => sum + (log.trail.distance_km ?? 0), 0);
  return [
    { id: "first-hike", title: "First steps", detail: "Log your first hike", earned: logs.length > 0, progress: Math.min(logs.length, 1) },
    { id: "first-overnight", title: "Under the stars", detail: "Log an overnight trip", earned: overnight, progress: overnight ? 1 : 0 },
    { id: "five-parks", title: "Park hopper", detail: `Hike in 5 parks or regions (${Math.min(parks, 5)} / 5)`, earned: parks >= 5, progress: Math.min(parks / 5, 1) },
    { id: "hundred-km", title: "Century", detail: `Hike ${formatDistance(100, units)} in total (${Math.floor(distanceValue(Math.min(km, 100), units))} / ${formatDistance(100, units)})`, earned: km >= 100, progress: Math.min(km / 100, 1) },
  ];
}

/** "Banff National Park" → "banff-national-park", for ?section= in the URL. */
export function slugify(title: string): string {
  return title
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * Lay out the book. `catalogue` is the live catalogue; retired trails appear
 * only if the user logged them, so their badges are kept.
 */
export function buildJournal(catalogue: TrailListItem[], logs: HikeLog[], units: UnitSystem = "metric"): Journal {
  const trails = new Map(catalogue.map((trail) => [trail.id, trail]));
  for (const log of logs) if (!trails.has(log.trail.id)) trails.set(log.trail.id, log.trail);
  const groups = groupTrails([...trails.values()]);

  const taken = new Set(["milestones"]);
  const sections: JournalSection[] = [{ kind: "contents", slug: null, title: "Contents" }];
  for (const group of groups) {
    const base = slugify(group.title) || "section";
    let slug = base;
    for (let n = 2; taken.has(slug); n += 1) slug = `${base}-${n}`;
    taken.add(slug);
    sections.push({ kind: "group", slug, title: group.title, group });
  }
  sections.push({ kind: "milestones", slug: "milestones", title: "Milestones" });

  const hikedIds = new Set(logs.map((log) => log.trail.id));
  return {
    groups,
    sections,
    hiked: [...trails.keys()].filter((id) => hikedIds.has(id)).length,
    total: trails.size,
    milestones: computeMilestones(logs, units),
  };
}

/** The section a ?section= value names; unknown or missing means the contents. */
export function sectionIndex(journal: Journal, slug: string | null): number {
  const index = slug ? journal.sections.findIndex((section) => section.slug === slug) : 0;
  return Math.max(index, 0);
}

/** Split a list across the two pages of a spread, the extra one on the left. */
export function halves<T>(items: T[]): [T[], T[]] {
  const cut = Math.ceil(items.length / 2);
  return [items.slice(0, cut), items.slice(cut)];
}

/** Columns and rows for `count` badges on one page (portrait, so never wider than 3). */
export function badgeGrid(count: number): { columns: number; rows: number } {
  const columns = count <= 1 ? 1 : count <= 6 ? 2 : 3;
  return { columns, rows: Math.max(1, Math.ceil(count / columns)) };
}
