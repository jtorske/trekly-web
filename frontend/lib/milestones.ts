import { distanceValue, formatElevation, formatWeight, formatWholeDistance, metersToFeet, type UnitSystem } from "./units.ts";

/**
 * Trail Journal milestones as the server sends them (backend
 * app/milestones.py; definitions in app/milestones_config.py). The server
 * decides what's earned; these pure helpers word the details and progress
 * in the reader's units and lay the milestones out as journal pages.
 */

export type Tier = "bronze" | "silver" | "gold";

export interface Milestone {
  /** null for a secret milestone not earned yet. */
  id: string | null;
  category: string;
  title: string;
  /** How to earn it; "{goal}" stands for `goal` in `unit`. */
  detail: string;
  goal: number | null;
  unit: "km" | "m" | "kg" | null;
  /** A short aside, e.g. "Counts trails with a known length." */
  note?: string | null;
  /** Can't be earned until the catalogue has more distance, elevation or route data. */
  needs_data?: boolean;
  /** null for a secret milestone not earned yet. */
  tier: Tier | null;
  icon: string;
  secret: boolean;
  earned: boolean;
  /** Only partway there (never at zero or once earned). */
  progress: { current: number; goal: number; unit: "km" | "m" | null; near: string | null } | null;
}

export interface MilestoneCategory {
  id: string;
  title: string;
}

export interface Milestones {
  categories: MilestoneCategory[];
  milestones: Milestone[];
  tier_points: Record<Tier, number>;
}

/** An earned milestone as a badge (featured badges, public profiles). */
export interface MilestoneBadgeInfo {
  id: string;
  category: string;
  title: string;
  tier: Tier;
  icon: string;
}

export const TIER_NAMES: Record<Tier, string> = { bronze: "Bronze", silver: "Silver", gold: "Gold" };

/** A key that's stable even for a hidden secret (which has no id). */
export function milestoneKey(milestone: Milestone, index: number): string {
  return milestone.id ?? `secret-${index}`;
}

function formatGoal(goal: number, unit: Milestone["unit"], units: UnitSystem): string {
  if (unit === "km") return formatWholeDistance(goal, units);
  if (unit === "m") return formatElevation(goal, units);
  if (unit === "kg") return formatWeight(goal * 1000, units);
  return goal.toLocaleString("en-US");
}

/** "Hike 100 km in total" (or "62 mi"). */
export function milestoneDetail(milestone: Milestone, units: UnitSystem = "metric"): string {
  if (milestone.goal == null) return milestone.detail;
  return milestone.detail.replaceAll("{goal}", formatGoal(milestone.goal, milestone.unit, units));
}

/** Whole display units, never showing the goal reached before it is (99.9 km is 62.07 mi, shown 61). */
function wholeOf(value: number, goal: number, toUnits: (n: number) => number): [number, number] {
  const shownGoal = Math.round(toUnits(goal));
  return [Math.min(Math.floor(toUnits(Math.min(value, goal))), shownGoal - 1), shownGoal];
}

/** "6 / 100 km", "8,000 / 8,849 m", "4 / 10", "2 / 3 in Banff National Park". */
export function progressLabel(milestone: Milestone, units: UnitSystem = "metric"): string | null {
  const progress = milestone.progress;
  if (!progress) return null;
  let current: number;
  let goal: number;
  let suffix = "";
  if (progress.unit === "km") {
    [current, goal] = wholeOf(progress.current, progress.goal, (km) => distanceValue(km, units));
    suffix = units === "metric" ? " km" : " mi";
  } else if (progress.unit === "m") {
    [current, goal] = wholeOf(progress.current, progress.goal, (m) => (units === "metric" ? m : metersToFeet(m)));
    suffix = units === "metric" ? " m" : " ft";
  } else {
    [current, goal] = [progress.current, progress.goal];
  }
  const near = progress.near ? ` in ${progress.near.replace(/,\s*[A-Z]{2}$/, "")}` : "";
  return `${current.toLocaleString("en-US")} / ${goal.toLocaleString("en-US")}${suffix}${near}`;
}

/** 0–1 for the progress arc. */
export function progressFraction(milestone: Milestone): number {
  if (milestone.earned) return 1;
  if (!milestone.progress) return 0;
  return Math.min(milestone.progress.current / milestone.progress.goal, 1);
}

export const earnedCount = (data: Milestones) => data.milestones.filter((m) => m.earned).length;

/** One page of the milestones part of the journal. */
export type MilestonePage =
  | { kind: "overview" }
  | {
      kind: "category";
      category: MilestoneCategory;
      /** This page's medals: all of the category's, or MEDALS_PER_PAGE of them. */
      milestones: Milestone[];
      /** A later page of a category too long for one. */
      continued: boolean;
    }
  | { kind: "blank" }
  | { kind: "back" };

/**
 * The most medals on one page: three rows of two. More would shrink them to
 * dots on a laptop screen, so a longer category (Exploration has ten)
 * carries on over the page under the same heading.
 */
export const MEDALS_PER_PAGE = 6;

/** A two-page spread: one section of the book. */
export interface MilestoneSpread {
  slug: string;
  title: string;
  left: MilestonePage;
  right: MilestonePage;
}

function categoryPages(data: Milestones, category: MilestoneCategory): MilestonePage[] {
  const all = data.milestones.filter((m) => m.category === category.id);
  const pages: MilestonePage[] = [];
  for (let start = 0; start === 0 || start < all.length; start += MEDALS_PER_PAGE) {
    pages.push({ kind: "category", category, milestones: all.slice(start, start + MEDALS_PER_PAGE), continued: start > 0 });
  }
  return pages;
}

/**
 * The overview, a page per category (two for a long one), and "Where to
 * next?" as the very last page, paired into spreads. An odd count gets a
 * blank page before the last so it still lands on the right.
 */
export function milestoneSpreads(data: Milestones): MilestoneSpread[] {
  const pages: MilestonePage[] = [{ kind: "overview" }, ...data.categories.flatMap((category) => categoryPages(data, category))];
  if (pages.length % 2 === 0) pages.push({ kind: "blank" });
  pages.push({ kind: "back" });

  const spreads: MilestoneSpread[] = [];
  for (let i = 0; i < pages.length; i += 2) {
    const [left, right] = [pages[i], pages[i + 1]];
    const shown = [left, right].flatMap((page) => (page.kind === "category" ? [page] : []));
    // Named after the first category that starts here; a spread of only a
    // continuation is that category's "-more".
    const starts = shown.filter((page) => !page.continued).map((page) => page.category);
    const slug = starts[0]?.id ?? (shown[0] ? `${shown[0].category.id}-more` : "end");
    const titles = [...new Set(shown.map((page) => page.category.title))];
    spreads.push({
      slug: i === 0 ? "milestones" : `milestones-${slug}`,
      title: i === 0 ? "Milestones" : `Milestones: ${titles.join(" and ") || "the end"}`,
      left,
      right,
    });
  }
  return spreads;
}

/** The section (?section=) where a category's first page is. */
export function categorySlug(data: Milestones, categoryId: string): string {
  const spread = milestoneSpreads(data).find((s) =>
    [s.left, s.right].some((page) => page.kind === "category" && page.category.id === categoryId && !page.continued),
  );
  return spread?.slug ?? "milestones";
}

/**
 * Milestones earned since `seen` (ids the user has already been told
 * about). With nothing seen yet (a first visit, or storage cleared) there
 * is no baseline, so nothing counts as new.
 */
export function newlyEarned(data: Milestones, seen: Set<string> | null): Milestone[] {
  if (!seen) return [];
  return data.milestones.filter((m) => m.earned && m.id && !seen.has(m.id));
}
