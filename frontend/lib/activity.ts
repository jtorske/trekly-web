import type { MilestoneBadgeInfo } from "./milestones";
import type { PrivacySettings } from "./profilesApi";
import type { TrailListItem } from "./trailsApi";

/**
 * The Activity feed: posts made from real activity (a shared hike, a
 * milestone, a new rank), never free-form. The API decides who appears:
 * only people with a public profile who turned on "Share my activity in the
 * feed", following their section switches and hidden dates. Trip plans,
 * alerts and future dates are never posted.
 */

export interface ActivityAuthor {
  username: string;
  display_name: string | null;
  avatar_path: string | null;
}

export interface ActivityPost {
  id: string;
  kind: "hike" | "milestone" | "rank";
  author: ActivityAuthor;
  /** null when the author hides their hike dates. */
  posted_at: string | null;
  hike: {
    trail: TrailListItem;
    /** null when hidden, or for a hike from before Trekly. */
    hiked_on: string | null;
    note: string | null;
    photo_path: string | null;
    verified: boolean;
  } | null;
  milestone: MilestoneBadgeInfo | null;
  rank: { level: number; title: string } | null;
  high_fives: number;
  high_fived: boolean;
  mine: boolean;
}

export interface ActivityPage {
  items: ActivityPost[];
  next_cursor: string | null;
  /** The viewer's home province, when signed in with one. */
  province: string | null;
}

export type ActivityScope = "everyone" | "province";

/** Why posts can't show in the feed, or null when sharing works. */
export function activityBlocker(
  settings: Pick<PrivacySettings, "is_private" | "show_journal" | "username">,
): string | null {
  if (!settings.username) return "You need a username before your activity can be shared.";
  if (settings.is_private) return "Your profile is private, so nothing is shared. Turn off Private profile to use this.";
  if (!settings.show_journal) {
    return "Your Trail Journal is hidden, so hikes and badges aren't shared. Turn on “Trail Journal and badges” to use this.";
  }
  return null;
}

/** Whether a newly logged hike can be shared right now (the dialog's checkbox). */
export function canShareHikes(
  settings: Pick<PrivacySettings, "is_private" | "show_journal" | "username" | "share_activity">,
): boolean {
  return settings.share_activity && activityBlocker(settings) === null;
}

/** Where tapping a post goes: the trail for a hike, the author's profile otherwise. */
export function postHref(post: Pick<ActivityPost, "kind" | "hike" | "author">): string {
  if (post.kind === "hike" && post.hike) return `/trails?id=${encodeURIComponent(post.hike.trail.id)}`;
  return `/u/${encodeURIComponent(post.author.username)}`;
}

/** The compact line for a milestone or rank post, after the author's name. */
export function postAction(post: Pick<ActivityPost, "kind" | "milestone" | "rank">): string {
  if (post.kind === "milestone" && post.milestone) return `earned ${post.milestone.title}`;
  if (post.kind === "rank" && post.rank) return `reached ${post.rank.title}`;
  return "hiked";
}

/** "now", "5m", "3h", "2d", then a short date. */
export function shortAgo(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60000);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return then.toLocaleDateString("en-CA", {
    month: "short",
    day: "numeric",
    ...(then.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  });
}

/** Appends a page, skipping posts already shown (a post can move pages as others are added). */
export function appendPage(current: ActivityPost[], next: ActivityPost[]): ActivityPost[] {
  const seen = new Set(current.map((post) => post.id));
  return [...current, ...next.filter((post) => !seen.has(post.id))];
}
