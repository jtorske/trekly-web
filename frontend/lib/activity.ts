import type { AccountLabel } from "./accountLabels";
import type { FollowState } from "./follows";
import type { Milestone, MilestoneBadgeInfo } from "./milestones";
import type { PrivacySettings } from "./profilesApi";
import type { TrailListItem } from "./trailsApi";

/**
 * The Activity feed: posts made from real activity (a shared hike, a
 * milestone, a new rank), never free-form, plus announcements from the
 * official @trekly account (written by admins). The API decides who appears:
 * only people with a public profile who turned on "Share my activity in the
 * feed", following their section switches and hidden dates. Trip plans,
 * alerts and future dates are never posted.
 */

export interface ActivityAuthor {
  username: string;
  display_name: string | null;
  avatar_path: string | null;
  /** "official" (Trekly team) or "demo" (Demo account): show the badge. */
  label?: AccountLabel | null;
  /** Signed in, and not your own post: whether you follow them. */
  follow: FollowState | null;
}

/** A milestone or rank a hike earned, shown inside that hike's post. */
export interface ActivityEarned {
  kind: "milestone" | "rank";
  milestone: MilestoneBadgeInfo | null;
  rank: { level: number; title: string } | null;
}

export interface ActivityPost {
  id: string;
  kind: "hike" | "milestone" | "rank" | "announcement";
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
  /** A post from the official Trekly account. */
  announcement?: {
    body: string;
    trail: TrailListItem | null;
    /** Public URL of the post's own photo. */
    photo_url: string | null;
  } | null;
  milestone: MilestoneBadgeInfo | null;
  rank: { level: number; title: string } | null;
  /** A hike post: what that hike earned (milestones, then the rank). */
  earned: ActivityEarned[];
  high_fives: number;
  high_fived: boolean;
  mine: boolean;
  /** Your own post that nobody else can see (sharing off, private profile…). */
  only_you: boolean;
}

export interface HighFivers {
  high_fives: number;
  /** Newest first; only hikers with a public profile. */
  hikers: ActivityAuthor[];
  /** Private profiles, and anyone past the list. */
  others: number;
}

/** A "Trekly pick" shown between posts while the feed is quiet. */
export interface FeedPick {
  kind: "trending" | "new_photos" | "seasonal";
  title: string;
  text: string;
  trail: TrailListItem;
}

export interface FeedPicks {
  /** Fewer than ~10 real posts this week: mix the picks in. */
  sparse: boolean;
  picks: FeedPick[];
}

/** Every how many posts a pick goes in. */
export const PICK_EVERY = 4;

/**
 * Posts with picks between them: one after every PICK_EVERY posts, and one
 * at the end of a shorter list, until the picks run out. Only while sparse.
 */
export function withPicks<P>(posts: P[], picks: FeedPicks | null): ({ post: P } | { pick: FeedPick })[] {
  const out: ({ post: P } | { pick: FeedPick })[] = [];
  const queue = picks?.sparse ? [...picks.picks] : [];
  posts.forEach((post, index) => {
    out.push({ post });
    if ((index + 1) % PICK_EVERY === 0 && queue.length) out.push({ pick: queue.shift()! });
  });
  if (queue.length && posts.length % PICK_EVERY !== 0) out.push({ pick: queue.shift()! });
  return out;
}

export interface TrendingTrail {
  trail: TrailListItem;
  /** false: a popular trail topping up a quiet week. */
  this_week: boolean;
}

export const ONLY_YOU_LABEL = "Only you can see this. Turn on sharing to post it.";

export interface ActivityPage {
  items: ActivityPost[];
  next_cursor: string | null;
  /** The viewer's home province, when signed in with one. */
  province: string | null;
  /** Signed in and following someone. */
  follows_anyone: boolean;
}

/** A profile's Activity tab, newest first. */
export interface ProfileActivityPage {
  items: ActivityPost[];
  next_cursor: string | null;
  /** All posts; on the first page only. */
  total: number | null;
  /** The owner's own view only: whether others can see their posts now. */
  sharing: boolean | null;
}

export type ActivityScope = "following" | "everyone" | "province";

/** Following is the default once you follow anyone; Everyone otherwise (and for guests). */
export function defaultScope(signedIn: boolean, followingCount: number | null | undefined): ActivityScope {
  return signedIn && (followingCount ?? 0) > 0 ? "following" : "everyone";
}

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
export function postHref(post: Pick<ActivityPost, "kind" | "hike" | "author" | "announcement">): string {
  if (post.kind === "hike" && post.hike) return `/trails?id=${encodeURIComponent(post.hike.trail.id)}`;
  if (post.kind === "announcement" && post.announcement?.trail) {
    return `/trails?id=${encodeURIComponent(post.announcement.trail.id)}`;
  }
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

/** "A", "A and B", "A, B and C". */
export function joinWords(words: string[]): string {
  if (words.length <= 1) return words[0] ?? "";
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

/** What a hike earned, as phrases after "Hiked <trail>": ["earned X and Y", "reached Z"]. */
export function earnedPhrases(earned: ActivityEarned[]): string[] {
  const milestones = earned.flatMap((e) => (e.kind === "milestone" && e.milestone ? [e.milestone.title] : []));
  const ranks = earned.flatMap((e) => (e.kind === "rank" && e.rank ? [e.rank.title] : []));
  return [
    ...(milestones.length ? [`earned ${joinWords(milestones)}`] : []),
    ...(ranks.length ? [`reached ${joinWords(ranks)}`] : []),
  ];
}

/** "Ben, @ana and 2 others high-fived this", for the high-five popover. */
export function highFiversLine(
  fivers: Pick<HighFivers, "hikers" | "others">,
  nameOf: (author: ActivityAuthor) => string,
): string {
  const names = fivers.hikers.map(nameOf);
  if (fivers.others > 0) names.push(fivers.others === 1 ? "1 other" : `${fivers.others} others`);
  return names.length ? `${joinWords(names)} high-fived this` : "No high fives yet";
}

/** The most recently earned milestone (by day earned, then journal order); null if none have a date. */
export function latestEarned(milestones: Milestone[]): Milestone | null {
  let best: Milestone | null = null;
  for (const milestone of milestones) {
    if (!milestone.earned || !milestone.earned_on || !milestone.id) continue;
    if (!best || milestone.earned_on > (best.earned_on ?? "")) best = milestone;
  }
  return best;
}

/** The Undo key for deleting a post (lists hide it while its toast is up). */
export const deleteKey = (postId: string) => `activity:${postId}`;
