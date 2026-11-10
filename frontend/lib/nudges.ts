import { activityBlocker } from "./activity.ts";
import { communityBlocker } from "./hikedBy.ts";
import type { PrivacySettings, PrivacyUpdate } from "./profilesApi.ts";

/**
 * Quiet pointers to the two community settings, "Share my activity in the
 * feed" and "Show me in community features". Both stay off until the user
 * taps a toggle; a nudge only offers it. The API decides which nudges show
 * (app/nudges.py) and keeps every dismissal, so one put away stays away on
 * every device. Turning a setting on goes through the privacy API, like
 * Settings → Privacy, and puts its nudges away too.
 */

export type Nudge = "hike_share" | "activity_card" | "hiked_by";

export const NUDGE_SETTING = {
  hike_share: "share_activity",
  activity_card: "share_activity",
  hiked_by: "show_in_community",
} as const satisfies Record<Nudge, keyof PrivacyUpdate>;

export interface NudgeApi {
  updatePrivacy: (update: PrivacyUpdate) => Promise<PrivacySettings>;
  dismissNudge: (nudge: Nudge) => Promise<void>;
}

/**
 * What a nudge can do, and only when called (a tap): turn its one setting on,
 * or put the nudge away. Nothing runs when this is made.
 */
export function nudgeActions(nudge: Nudge, api: NudgeApi) {
  return {
    turnOn: () => api.updatePrivacy({ [NUDGE_SETTING[nudge]]: true }),
    dismiss: () => api.dismissNudge(nudge),
  };
}

type Summarised = Pick<
  PrivacySettings,
  | "username"
  | "is_private"
  | "show_journal"
  | "show_rank"
  | "show_gear"
  | "show_saved_trails"
  | "show_trip_plans"
  | "show_home_province"
  | "show_visit_streak"
  | "show_in_community"
  | "share_activity"
>;

export type VisitorItemKey = keyof Omit<Summarised, "username" | "is_private">;

/** Each thing visitors may see, in Settings → Privacy order, with its short name. */
export const VISITOR_ITEMS: { key: VisitorItemKey; label: string; community?: true }[] = [
  { key: "show_journal", label: "Journal" },
  { key: "show_rank", label: "Rank" },
  { key: "show_gear", label: "Gear" },
  { key: "show_saved_trails", label: "Saved trails" },
  { key: "show_trip_plans", label: "Trip plans" },
  { key: "show_home_province", label: "Home province" },
  { key: "show_visit_streak", label: "Visit streak" },
  { key: "share_activity", label: "Activity feed", community: true },
  { key: "show_in_community", label: "Hiked by", community: true },
];

/** Why a community setting can't take effect now, or null. */
export function itemBlocker(settings: Summarised, key: VisitorItemKey): string | null {
  if (key === "share_activity") return activityBlocker(settings);
  if (key === "show_in_community") return settings.username ? communityBlocker(settings) : activityBlocker(settings);
  return null;
}

/** Whether visitors actually see it: switched on, and nothing (private, hidden journal) stopping it. */
export function itemVisible(settings: Summarised, key: VisitorItemKey): boolean {
  return !settings.is_private && Boolean(settings.username) && settings[key] && itemBlocker(settings, key) === null;
}

export function visitorSummary(settings: Summarised): { visible: string[]; hidden: string[] } {
  const visible: string[] = [];
  const hidden: string[] = [];
  for (const item of VISITOR_ITEMS) (itemVisible(settings, item.key) ? visible : hidden).push(item.label);
  return { visible, hidden };
}


/**
 * The one line at the top of Settings → Privacy, e.g.
 * "Visitors see: journal, rank, gear. Not sharing: Activity feed, Hiked by."
 */
export function summaryLine(settings: Summarised): string {
  if (!settings.username) return "Visitors can't see your profile until you choose a username.";
  if (settings.is_private) return "Your profile is private: visitors see only your name, username and photo.";
  const profile = VISITOR_ITEMS.filter((item) => !item.community);
  const community = VISITOR_ITEMS.filter((item) => item.community);
  const seen = profile.filter((item) => itemVisible(settings, item.key)).map((item) => item.label.toLowerCase());
  const notSharing = community.filter((item) => !itemVisible(settings, item.key)).map((item) => item.label);
  const parts = [seen.length > 0 ? `Visitors see: ${seen.join(", ")}.` : "Visitors see your name, username, photo and bio only."];
  if (notSharing.length > 0) parts.push(`Not sharing: ${notSharing.join(", ")}.`);
  else parts.push("Sharing: Activity feed, Hiked by.");
  return parts.join(" ");
}
