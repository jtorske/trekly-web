import type { HikeLog } from "./hikeLogsApi";
import type { TrailListItem } from "./trailsApi";

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
export const BADGES_PER_PAGE = 6;

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

export type JournalPage =
  | { kind: "cover" }
  /** The contents run across the first spread; part 1 ends with the badge key. */
  | { kind: "contents"; groups: JournalGroup[]; part: 0 | 1 }
  | { kind: "group"; group: JournalGroup; trails: TrailListItem[]; part: number; parts: number }
  | { kind: "milestones" }
  | { kind: "back" };

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
  pages: JournalPage[];
  /** Page index where each group starts (always a left-hand page). */
  groupStart: Map<string, number>;
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

function chunk<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) chunks.push(items.slice(i, i + size));
  return chunks.length ? chunks : [[]];
}

export function computeMilestones(logs: HikeLog[]): Milestone[] {
  const overnight = logs.some((log) => (log.trail.typical_duration_nights ?? 0) >= 1);
  const parks = new Set(logs.map((log) => log.trail.region)).size;
  // Only trails with a known distance count towards the total.
  const km = logs.reduce((sum, log) => sum + (log.trail.distance_km ?? 0), 0);
  return [
    { id: "first-hike", title: "First steps", detail: "Log your first hike", earned: logs.length > 0, progress: Math.min(logs.length, 1) },
    { id: "first-overnight", title: "Under the stars", detail: "Log an overnight trip", earned: overnight, progress: overnight ? 1 : 0 },
    { id: "five-parks", title: "Park hopper", detail: `Hike in 5 parks or regions (${Math.min(parks, 5)} / 5)`, earned: parks >= 5, progress: Math.min(parks / 5, 1) },
    { id: "hundred-km", title: "Century", detail: `Hike 100 km in total (${Math.floor(Math.min(km, 100))} / 100 km)`, earned: km >= 100, progress: Math.min(km / 100, 1) },
  ];
}

/**
 * Lay out the book. `catalogue` is the live catalogue; retired trails appear
 * only if the user logged them, so their badges are kept.
 *
 * Page 0 is the cover (alone on the right of a desktop spread), so every
 * odd page is a left-hand page. Groups start on a left page and fill whole
 * spreads.
 */
export function buildJournal(catalogue: TrailListItem[], logs: HikeLog[]): Journal {
  const trails = new Map(catalogue.map((trail) => [trail.id, trail]));
  for (const log of logs) if (!trails.has(log.trail.id)) trails.set(log.trail.id, log.trail);
  const groups = groupTrails([...trails.values()]);

  const half = Math.ceil(groups.length / 2);
  const pages: JournalPage[] = [
    { kind: "cover" },
    { kind: "contents", groups: groups.slice(0, half), part: 0 },
    { kind: "contents", groups: groups.slice(half), part: 1 },
  ];
  const groupStart = new Map<string, number>();
  for (const group of groups) {
    groupStart.set(group.key, pages.length);
    const chunks = chunk(group.trails, BADGES_PER_PAGE);
    if (chunks.length % 2) chunks.push([]);
    chunks.forEach((part, index) =>
      pages.push({ kind: "group", group, trails: part, part: index, parts: chunks.length }),
    );
  }
  pages.push({ kind: "milestones" }, { kind: "back" });

  const hikedIds = new Set(logs.map((log) => log.trail.id));
  return {
    groups,
    pages,
    groupStart,
    hiked: [...trails.keys()].filter((id) => hikedIds.has(id)).length,
    total: trails.size,
    milestones: computeMilestones(logs),
  };
}

/** Desktop spreads: spread 0 is [-, cover], spread k is [2k-1, 2k]. */
export const spreadOfPage = (page: number) => Math.ceil(page / 2);
export const spreadPages = (spread: number): [number, number] => [spread * 2 - 1, spread * 2];
export const spreadCount = (pages: number) => spreadOfPage(pages - 1) + 1;
