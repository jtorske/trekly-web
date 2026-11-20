import type { ReviewState } from "./moderation";
import type { AccountLabel } from "./accountLabels";
import type { FollowState } from "./follows";
import type { Milestone, MilestoneBadgeInfo } from "./milestones";
import type { PrivacySettings } from "./profilesApi";
import type { TrailListItem } from "./trailsApi";
import type { HikerResult } from "./hikerSearch";
import { trailHref } from "./site.ts";

/**
 * The Activity feed: posts made from real activity (a shared hike, a
 * milestone, a new rank), never free-form, plus announcements from the
 * official @trekly account (written by admins). One blended feed, arranged
 * by the API (backend app/feed.py): people you follow first, then
 * suggestions, with Trekly picks so it's never empty. The API decides who appears:
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
    /** The official page an automatic post quotes or cites (a Parks Canada bulletin, a fact's source). */
    source_url?: string | null;
    source_label?: string | null;
    /** YYYY-MM-DD: when the source was issued (a bulletin's date). */
    source_date?: string | null;
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
  /** Your own hike (or what it earned) that you never shared: only you see it, whatever your settings. */
  unshared?: boolean;
  /** Your own post only: held for review, or removed by a moderator (lib/moderation.ts). */
  review?: ReviewState | null;
  /** The Activity feed only: why it's in your feed ("suggested": "Suggested for you" and a Follow button). */
  reason?: FeedReason | null;
  /** Comments this reader can see, and the newest two (oldest first). */
  comment_count?: number;
  comments?: ActivityComment[];
  /** Its author turned comments off. */
  comments_off?: boolean;
  /** Signed in and comments are on (posting checks the rest). */
  can_comment?: boolean;
}

/** A comment on a post (backend app/comments.py). Plain text; links aren't links. */
export interface ActivityComment {
  id: string;
  /** A reply: the top-level comment it's under. */
  parent_id: string | null;
  author: Omit<ActivityAuthor, "follow">;
  body: string;
  created_at: string;
  /** Set once its author changed it. */
  edited_at: string | null;
  mine: boolean;
  /** Yours, or on your post. */
  can_delete: boolean;
  /** Your own, held by moderation ("pending") or removed ("hidden"). */
  review?: ReviewState | null;
}

export interface CommentList {
  comments: ActivityComment[];
  count: number;
  comments_off: boolean;
  can_comment: boolean;
  post_mine: boolean;
}

export const COMMENT_LIMIT = 500;

/** "1 comment", "14 comments". */
export function commentCount(count: number): string {
  return `${count} comment${count === 1 ? "" : "s"}`;
}

/** The link under a post's preview: "View all 14 comments", or null when the preview shows them all. */
export function viewAllLabel(count: number, shown: number): string | null {
  if (count <= shown) return null;
  return count === 2 ? "View both comments" : `View all ${count} comments`;
}

/** What a reply box starts with: "@ana " (unless it already mentions them). */
export function replyPrefix(username: string, current = ""): string {
  const mention = `@${username}`;
  const already = new RegExp(`(^|\\s)${mention}(?![\\w])`, "i");
  if (already.test(current)) return current;
  return current ? `${mention} ${current}` : `${mention} `;
}

/** A comment as the server keeps it: trimmed, plain newlines, at most one blank line in a row. */
export function cleanComment(text: string): string {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** The Undo key for deleting a comment. */
export const commentDeleteKey = (commentId: string) => `comment:${commentId}`;

/** A post's own page (comments in full). */
export const postPagePath = (postId: string) => `/activity/${encodeURIComponent(postId)}`;

export type FeedReason = "own" | "following" | "suggested" | "trekly" | "demo";

export interface HighFivers {
  high_fives: number;
  /** Newest first; only hikers with a public profile. */
  hikers: ActivityAuthor[];
  /** Private profiles, and anyone past the list. */
  others: number;
}

/** A "Trekly pick": mixed in while the feed is quiet, and closing it. */
export interface FeedPick {
  kind: "trending" | "new_photos" | "seasonal";
  title: string;
  text: string;
  trail: TrailListItem;
}

export interface TrendingTrail {
  trail: TrailListItem;
  /** false: a popular trail topping up a quiet week. */
  this_week: boolean;
}

export const ONLY_YOU_LABEL = "Only you can see this. Turn on sharing to post it.";
/** On a hike you never shared: sharing your activity doesn't show it. */
export const UNSHARED_LABEL = "Only you can see this hike. You haven't shared it.";

/** One slot in the feed, in order: a post (by id), the "caught up" divider, or a Trekly pick. */
export type FeedEntry =
  | { type: "post"; post_id: string; pick?: null }
  | { type: "caught_up"; post_id?: null; pick?: null }
  | { type: "pick"; post_id?: null; pick: FeedPick };

export interface ActivityPage {
  /** This page's posts, in feed order. */
  items: ActivityPost[];
  /** The page in order: posts by id, with the divider and picks between them. */
  entries: FeedEntry[];
  next_cursor: string | null;
  /** When the feed was arranged; the "New posts" pill counts from here. */
  as_of: string;
  /** Signed in and following someone. */
  follows_anyone: boolean;
  /** The first page, signed in and following nobody: hikers to follow. */
  suggested_hikers: HikerResult[] | null;
}

/** The feed so far: its entries in order, and the posts they point at. */
export interface FeedState {
  entries: FeedEntry[];
  posts: Record<string, ActivityPost>;
}

const entryKey = (entry: FeedEntry) =>
  entry.type === "post" ? `post:${entry.post_id}` : entry.type === "pick" ? `pick:${entry.pick.kind}:${entry.pick.trail.id}` : "caught_up";

/**
 * Adds a page to the feed (or starts it, with `current` null), never showing
 * a post, pick or the divider twice in one visit.
 */
export function mergeFeedPage(current: FeedState | null, page: Pick<ActivityPage, "items" | "entries">): FeedState {
  const posts = { ...(current?.posts ?? {}) };
  const seen = new Set((current?.entries ?? []).map(entryKey));
  const entries = [...(current?.entries ?? [])];
  const fresh = new Map(page.items.map((post) => [post.id, post]));
  for (const entry of page.entries) {
    const key = entryKey(entry);
    if (seen.has(key)) continue;
    if (entry.type === "post") {
      const post = fresh.get(entry.post_id);
      if (!post) continue;
      posts[post.id] = post;
    }
    seen.add(key);
    entries.push(entry);
  }
  return { entries, posts };
}

export type FeedRow =
  | { type: "post"; key: string; post: ActivityPost }
  | { type: "caught_up"; key: string }
  | { type: "pick"; key: string; pick: FeedPick }
  | { type: "follow_prompt"; key: string };

/** Where the "Follow hikers" card goes: after this many rows. */
export const FOLLOW_PROMPT_AT = 2;

/**
 * The rows to draw: the feed's entries, less posts that are hidden (a pending
 * delete), with the "Follow hikers" card near the top when asked for. A
 * divider with nothing after it yet stays; one with nothing before it goes.
 */
export function feedRows(
  feed: FeedState,
  { hidden = () => false, followPrompt = false }: { hidden?: (postId: string) => boolean; followPrompt?: boolean } = {},
): FeedRow[] {
  const rows: FeedRow[] = [];
  for (const entry of feed.entries) {
    if (entry.type === "post") {
      const post = feed.posts[entry.post_id];
      if (post && !hidden(post.id)) rows.push({ type: "post", key: post.id, post });
    } else if (entry.type === "pick") {
      rows.push({ type: "pick", key: entryKey(entry), pick: entry.pick });
    } else if (rows.some((row) => row.type === "post")) {
      rows.push({ type: "caught_up", key: "caught_up" });
    }
  }
  if (followPrompt) rows.splice(Math.min(FOLLOW_PROMPT_AT, rows.length), 0, { type: "follow_prompt", key: "follow_prompt" });
  return rows;
}

/** A profile's Activity tab, newest first. */
export interface ProfileActivityPage {
  items: ActivityPost[];
  next_cursor: string | null;
  /** All posts; on the first page only. */
  total: number | null;
  /** The owner's own view only: whether others can see their posts now. */
  sharing: boolean | null;
  /** The owner's first page only: hikes the one-time "Share your past hikes?" prompt offers (0: don't ask). */
  past_hikes?: number | null;
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
  if (post.kind === "hike" && post.hike) return trailHref(post.hike.trail);
  if (post.kind === "announcement" && post.announcement?.trail) {
    return trailHref(post.announcement.trail);
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

/** "November 9, 2026" from a YYYY-MM-DD date, read as a calendar day (no time zone shift). */
export function formatSourceDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-CA", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}
