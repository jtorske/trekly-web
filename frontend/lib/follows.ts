import type { AccountLabel } from "./accountLabels";
/**
 * Following. A public profile is followed at once; a private one gets a
 * request its owner approves or declines. Approved followers of a private
 * profile see the sections its owner shows. The API enforces all of it
 * (app/follows.py); nothing here hides anything.
 */

/** The viewer's state toward someone. null: it's you, or you're signed out. */
export type FollowState = "none" | "requested" | "following";

export interface Person {
  username: string;
  display_name: string | null;
  avatar_path: string | null;
  /** "official" or "demo": show the badge. */
  label?: AccountLabel | null;
  is_private: boolean;
  follow: FollowState | null;
}

export interface PeoplePage {
  items: Person[];
  next_cursor: string | null;
}

export type FollowList = "followers" | "following";

/** What the follow button says, and does when pressed. */
export function followButton(state: FollowState, isPrivate: boolean): { label: string; next: "follow" | "unfollow" } {
  if (state === "following") return { label: "Following", next: "unfollow" };
  if (state === "requested") return { label: "Requested", next: "unfollow" };
  return { label: isPrivate ? "Request to follow" : "Follow", next: "follow" };
}

/** "1 follower", "12 followers", "1,204 following". */
export function countLabel(count: number, which: FollowList): string {
  const n = count.toLocaleString("en-CA");
  if (which === "following") return `${n} following`;
  return `${n} ${count === 1 ? "follower" : "followers"}`;
}

/** The toast after a follow or unfollow. */
export function followToast(before: FollowState, after: FollowState, name: string): string | null {
  if (after === "following" && before !== "following") return `You're following ${name}.`;
  if (after === "requested") return `Request sent. You'll follow ${name} once they approve it.`;
  if (before === "requested" && after === "none") return "Request cancelled.";
  if (before === "following" && after === "none") return `You unfollowed ${name}.`;
  return null;
}

const FOLLOW_EVENT = "trekly:follow-changed";

/** Tells every follow button on the page about a change, so they agree. */
export function announceFollow(username: string, follow: FollowState) {
  window.dispatchEvent(new CustomEvent(FOLLOW_EVENT, { detail: { username, follow } }));
}

export function onFollowChanged(listener: (username: string, follow: FollowState) => void): () => void {
  const handler = (event: Event) => {
    const { username, follow } = (event as CustomEvent<{ username: string; follow: FollowState }>).detail;
    listener(username, follow);
  };
  window.addEventListener(FOLLOW_EVENT, handler);
  return () => window.removeEventListener(FOLLOW_EVENT, handler);
}
