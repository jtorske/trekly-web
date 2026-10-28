import type { PrivacySettings } from "./profilesApi";

/**
 * "Hiked by" on trail pages: opted-in hikers who logged a trail, and a few
 * of their trip notes. The API lists only people whose profile and Trail
 * Journal are public and who turned on "Show me in community features";
 * row-level security applies the same rule to direct Supabase access.
 */

export interface CommunityHiker {
  username: string;
  display_name: string | null;
  avatar_path: string | null;
}

export interface CommunityNote extends CommunityHiker {
  note: string;
  /** null when they hide the dates of their hikes. */
  hiked_on: string | null;
  /** A photo already visible on their public journal. */
  photo_path: string | null;
}

export interface TrailHikers {
  hikers: CommunityHiker[];
  /** How many more hikers there are beyond `hikers`. */
  others: number;
  notes: CommunityNote[];
}

export function othersLabel(others: number): string | null {
  if (others <= 0) return null;
  return `and ${others.toLocaleString()} ${others === 1 ? "other" : "others"}`;
}

export const NOTE_PREVIEW_CHARS = 160;

/** The note cut at a word near `limit`, with an ellipsis, or null if it fits. */
export function shortenNote(note: string, limit = NOTE_PREVIEW_CHARS): string | null {
  const text = note.trim();
  if (text.length <= limit) return null;
  const cut = text.slice(0, limit);
  const space = cut.lastIndexOf(" ");
  return `${(space > limit * 0.6 ? cut.slice(0, space) : cut).trimEnd().replace(/[.,;:!?-]+$/, "")}…`;
}

/** Why "Show me in community features" can't take effect, or null when it can. */
export function communityBlocker(settings: Pick<PrivacySettings, "is_private" | "show_journal">): string | null {
  if (settings.is_private) return "Your profile is private, so you won't appear. Turn off Private profile to use this.";
  if (!settings.show_journal) {
    return "Your Trail Journal is hidden, so you won't appear. Turn on “Trail Journal and badges” to use this.";
  }
  return null;
}
