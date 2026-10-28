import type { HikeLog } from "./hikeLogsApi";
import { computeMilestones, regionTitle, type Milestone } from "./journal.ts";
import type { TrailListItem } from "./trailsApi";

/**
 * Featured badges: up to three earned badges shown on a profile. The API
 * (backend app/featured.py) decides what's earned and what shows; these
 * pure helpers drive the picker. Requests are in featuredBadgesApi.ts.
 */

export const MAX_FEATURED = 3;

export type MilestoneId = Milestone["id"];

export type FeaturedBadge =
  | { kind: "trail"; trail: TrailListItem; milestone?: null }
  | { kind: "milestone"; milestone: MilestoneId; trail?: null };

export interface FeaturedBadges {
  /** false: nothing picked, so these are the most recent trail badges. */
  picked: boolean;
  badges: FeaturedBadge[];
}

/** A stable key: "trail:<id>" or "milestone:<id>". */
export function badgeKey(badge: FeaturedBadge): string {
  return badge.kind === "trail" ? `trail:${badge.trail.id}` : `milestone:${badge.milestone}`;
}

export function badgeName(badge: FeaturedBadge): string {
  if (badge.kind === "trail") return badge.trail.name;
  return computeMilestones([]).find((m) => m.id === badge.milestone)?.title ?? badge.milestone;
}

export interface BadgeGroup {
  title: string;
  badges: FeaturedBadge[];
}

/**
 * Everything the user can feature: milestones they've earned first, then
 * their trail badges grouped by park or region (A–Z, trails A–Z within).
 * `query` filters by trail, region or milestone name.
 */
export function earnedBadgeGroups(logs: HikeLog[], query = ""): BadgeGroup[] {
  const needle = query.trim().toLowerCase();
  const matches = (...texts: string[]) => !needle || texts.some((text) => text.toLowerCase().includes(needle));

  const milestones = computeMilestones(logs)
    .filter((m) => m.earned && matches(m.title, "milestone"))
    .map((m): FeaturedBadge => ({ kind: "milestone", milestone: m.id }));

  const regions = new Map<string, FeaturedBadge[]>();
  for (const { trail } of logs) {
    const title = regionTitle(trail.region);
    if (!matches(trail.name, title)) continue;
    regions.set(title, [...(regions.get(title) ?? []), { kind: "trail", trail }]);
  }
  const groups = [...regions.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([title, badges]) => ({ title, badges: badges.sort((a, b) => badgeName(a).localeCompare(badgeName(b))) }));

  return milestones.length ? [{ title: "Milestones", badges: milestones }, ...groups] : groups;
}

/** Add or remove a badge; adding past the limit does nothing (the picker says why). */
export function toggleBadge(selected: FeaturedBadge[], badge: FeaturedBadge, max = MAX_FEATURED): FeaturedBadge[] {
  const key = badgeKey(badge);
  if (selected.some((b) => badgeKey(b) === key)) return selected.filter((b) => badgeKey(b) !== key);
  return selected.length >= max ? selected : [...selected, badge];
}

/** Move the badge at `from` to `to` (clamped), for drag and the up/down buttons. */
export function moveBadge(selected: FeaturedBadge[], from: number, to: number): FeaturedBadge[] {
  const target = Math.max(0, Math.min(selected.length - 1, to));
  if (from === target || from < 0 || from >= selected.length) return selected;
  const next = [...selected];
  const [badge] = next.splice(from, 1);
  next.splice(target, 0, badge);
  return next;
}
