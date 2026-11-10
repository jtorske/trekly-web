import type { FollowState } from "./follows";

/**
 * In-app notifications. The API makes and groups them (app/notifications.py):
 * new followers on the same day, and high fives or comments on the same
 * post, arrive as one item. Read state lives on the server.
 */

export type NotificationKind = "new_follower" | "follow_request" | "request_approved" | "high_five" | "comment";

export interface NotificationActor {
  username: string;
  display_name: string | null;
  avatar_path: string | null;
}

export interface TreklyNotification {
  id: string;
  /** Every notification in the group, for marking it read. */
  ids: string[];
  kind: NotificationKind;
  /** The newest few. */
  actors: NotificationActor[];
  /** Everyone in the group. */
  actor_count: number;
  created_at: string;
  unread: boolean;
  post: { id: string; kind: "hike" | "milestone" | "rank"; title: string; trail_id: string | null } | null;
  /** A one-person item: your follow state toward them ("Follow back"). */
  follow: FollowState | null;
}

export interface NotificationList {
  items: TreklyNotification[];
  unread: number;
}

export type NotificationPreferences = Record<NotificationKind, boolean>;

/** Settings → Notifications, in this order. */
export const NOTIFICATION_TYPES: { kind: NotificationKind; label: string; hint: string }[] = [
  { kind: "new_follower", label: "New followers", hint: "When someone follows you." },
  { kind: "follow_request", label: "Follow requests", hint: "When someone asks to follow your private profile. Requests still wait for you on your profile." },
  { kind: "request_approved", label: "Accepted requests", hint: "When someone approves your request to follow them." },
  { kind: "high_five", label: "High fives", hint: "When someone high-fives one of your posts." },
  { kind: "comment", label: "Comments", hint: "When someone comments on one of your posts." },
];

const nameOf = (actor: NotificationActor) => actor.display_name?.trim() || `@${actor.username}`;

/** "Ana", "Ana and Ben", "Ana and 3 others". */
export function whoText(actors: NotificationActor[], count: number): string {
  if (actors.length === 0) return "Someone";
  const first = nameOf(actors[0]);
  if (count <= 1) return first;
  if (count === 2 && actors[1]) return `${first} and ${nameOf(actors[1])}`;
  return `${first} and ${count - 1} others`;
}

/** "your hike on Bald Hills", "your Double header badge", "reaching Day Tripper". */
export function postText(post: TreklyNotification["post"]): string {
  if (!post) return "your post";
  if (post.kind === "hike") return `your hike on ${post.title}`;
  if (post.kind === "milestone") return `your ${post.title} badge`;
  return `your new rank, ${post.title}`;
}

/** What happened, after the names. */
export function actionText(item: Pick<TreklyNotification, "kind" | "post">): string {
  switch (item.kind) {
    case "new_follower":
      return "started following you";
    case "follow_request":
      return "asked to follow you";
    case "request_approved":
      return "approved your follow request";
    case "high_five":
      return `high-fived ${postText(item.post)}`;
    case "comment":
      return `commented on ${postText(item.post)}`;
  }
}

/** Where tapping the item goes. */
export function notificationHref(item: Pick<TreklyNotification, "kind" | "post" | "actors" | "actor_count">): string {
  if ((item.kind === "high_five" || item.kind === "comment") && item.post) {
    if (item.kind === "comment") return `/activity?post=${encodeURIComponent(item.post.id)}`;
    return item.post.trail_id ? `/trails?id=${encodeURIComponent(item.post.trail_id)}` : "/profile";
  }
  if (item.actor_count === 1 && item.actors[0]) return `/u/${encodeURIComponent(item.actors[0].username)}`;
  return "/profile";
}

/** The badge: "9+" past nine; nothing at zero. */
export function badgeText(unread: number): string | null {
  if (unread <= 0) return null;
  return unread > 9 ? "9+" : String(unread);
}

const UNREAD_EVENT = "trekly:notifications-unread";

/** Tells the bell (and the menu) the new unread count, e.g. after marking read. */
export function announceUnread(unread: number) {
  window.dispatchEvent(new CustomEvent(UNREAD_EVENT, { detail: unread }));
}

export function onUnreadChanged(listener: (unread: number) => void): () => void {
  const handler = (event: Event) => listener((event as CustomEvent<number>).detail);
  window.addEventListener(UNREAD_EVENT, handler);
  return () => window.removeEventListener(UNREAD_EVENT, handler);
}
