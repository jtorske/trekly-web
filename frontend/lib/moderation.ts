/**
 * Moderation as the author sees it (the API, app/moderation.py): content
 * the automated check flagged, or enough people reported, is "pending"
 * until a moderator reviews it; "hidden" once a moderator removed it.
 * Either way only its author sees it.
 */
export type ReviewState = "pending" | "hidden";

export const APPEAL_EMAIL = "treklyusersupport@gmail.com";

export function reviewMessage(state: ReviewState, what = "post"): string {
  return state === "pending"
    ? `Your ${what} is being reviewed. Only you can see it until a moderator checks it.`
    : `A moderator removed your ${what}. Only you can see it.`;
}

/** "note", "photo", "note and photo": the parts of a hike being held. */
export function partsLabel(parts: string[], fallback = "post"): string {
  const words = parts.map((part) => (part === "avatar" ? "profile photo" : part));
  if (words.length === 0) return fallback;
  return words.length === 1 ? words[0] : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}
