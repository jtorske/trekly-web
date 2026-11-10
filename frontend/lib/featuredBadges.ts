import type { HikeLog } from "./hikeLogsApi";
import { regionTitle } from "./journal.ts";
import type { MilestoneBadgeInfo, Milestones } from "./milestones.ts";
import { homeLabel, province as findProvince, type HomeCode } from "./provinces.ts";
import type { TrailListItem } from "./trailsApi";

/**
 * Featured badges: up to three earned badges shown on a profile. The API
 * (backend app/featured.py) decides what's earned and what shows; these
 * pure helpers drive the picker. Requests are in featuredBadgesApi.ts.
 */

export const MAX_FEATURED = 3;

export type FeaturedBadge =
  /** `hiked_on`: the latest dated hike; null for one from before Trekly, or while dates are hidden. */
  | { kind: "trail"; trail: TrailListItem; hiked_on?: string | null; milestone?: null; badge?: null }
  /** `badge` is the milestone's name, tier and icon. */
  | { kind: "milestone"; milestone: string; badge: MilestoneBadgeInfo; trail?: null }
  /** The home province badge; only sent to viewers who may see the province. */
  | { kind: "province"; province: HomeCode; trail?: null; milestone?: null; badge?: null };

export interface FeaturedBadges {
  /** false: nothing picked, so these are the most recent trail badges. */
  picked: boolean;
  badges: FeaturedBadge[];
}

/** A stable key: "trail:<id>", "milestone:<id>" or "province". */
export function badgeKey(badge: FeaturedBadge): string {
  if (badge.kind === "province") return "province";
  return badge.kind === "trail" ? `trail:${badge.trail.id}` : `milestone:${badge.milestone}`;
}

export function badgeName(badge: FeaturedBadge): string {
  if (badge.kind === "trail") return badge.trail.name;
  if (badge.kind === "province") return findProvince(badge.province)?.name ?? badge.province;
  return badge.badge.title;
}

export interface BadgeGroup {
  title: string;
  badges: FeaturedBadge[];
}

/**
 * Everything the user can feature: milestones they've earned first (in
 * journal order), then their home province badge if they've chosen one,
 * then their trail badges grouped by park or region (A–Z, trails A–Z
 * within). `query` filters by trail, region, milestone or province name.
 */
export function earnedBadgeGroups(
  logs: HikeLog[],
  milestones: Milestones | null,
  query = "",
  homeProvince: HomeCode | null = null,
): BadgeGroup[] {
  const needle = query.trim().toLowerCase();
  const matches = (...texts: string[]) => !needle || texts.some((text) => text.toLowerCase().includes(needle));

  const earned = (milestones?.milestones ?? []).flatMap((m): FeaturedBadge[] =>
    m.earned && m.id && m.tier && matches(m.title, "milestone")
      ? [{ kind: "milestone", milestone: m.id, badge: { id: m.id, category: m.category, title: m.title, tier: m.tier, icon: m.icon } }]
      : [],
  );

  const regions = new Map<string, FeaturedBadge[]>();
  for (const { trail } of logs) {
    const title = regionTitle(trail.region);
    if (!matches(trail.name, title)) continue;
    regions.set(title, [...(regions.get(title) ?? []), { kind: "trail", trail }]);
  }
  const groups = [...regions.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([title, badges]) => ({ title, badges: badges.sort((a, b) => badgeName(a).localeCompare(badgeName(b))) }));

  const home = findProvince(homeProvince);
  const homeGroup: BadgeGroup[] =
    home && matches(home.name, homeLabel(home)) ? [{ title: homeLabel(home), badges: [{ kind: "province", province: home.code }] }] : [];

  return [...(earned.length ? [{ title: "Milestones", badges: earned }] : []), ...homeGroup, ...groups];
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
