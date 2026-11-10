import type { PrivacySettings, PublicProfile } from "./profilesApi";

/**
 * Pure helpers for the public profile page (/u/[username]). Everything they
 * read came from the API's visitor view, so nothing here can reveal more
 * than the owner allowed.
 */

export const SECTION_LABELS = {
  show_journal: "Trail Journal and badges",
  show_rank: "Rank",
  show_gear: "Gear and loadouts",
  show_saved_trails: "Saved trails",
  show_trip_plans: "Trip plans",
} as const;

export type SectionSetting = keyof typeof SECTION_LABELS;

/** For the owner's banner: which sections visitors don't see. */
export function hiddenSections(settings: PrivacySettings): string[] {
  return (Object.keys(SECTION_LABELS) as SectionSetting[]).filter((key) => !settings[key]).map((key) => SECTION_LABELS[key]);
}

/** Search engines may index a profile only when its owner opted in (and it isn't private). */
export function robotsFor(profile: Pick<PublicProfile, "allow_indexing"> | null): { index: boolean; follow: boolean } {
  const allowed = Boolean(profile?.allow_indexing);
  return { index: allowed, follow: allowed };
}

export function displayName(profile: Pick<PublicProfile, "display_name" | "username">): string {
  return profile.display_name?.trim() || `@${profile.username}`;
}

/** "14 August 2026" for a plain YYYY-MM-DD date, without a time-zone shift. */
export function formatHikeDate(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(year, month - 1, date).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

/**
 * "Joined October 2026", from the owner's own sign-up timestamp or the public
 * profile's month ("2026-10", read as a calendar month so no time zone can
 * move it into September).
 */
export function joinedLabel(joined: string | null | undefined): string | null {
  if (!joined) return null;
  const month = /^(\d{4})-(\d{2})$/.exec(joined);
  const when = month ? new Date(Number(month[1]), Number(month[2]) - 1, 1) : new Date(joined);
  if (Number.isNaN(when.getTime())) return null;
  return `Joined ${when.toLocaleDateString(undefined, { month: "long", year: "numeric" })}`;
}

/**
 * A trail badge's card line: "Hiked November 9, 2026", "Hiked before Trekly"
 * for a hike with no date, or nothing while the owner hides their dates.
 */
export function trailBadgeHiked(hikedOn: string | null | undefined, datesHidden: boolean): string | null {
  if (hikedOn) return `Hiked ${formatHikeDate(hikedOn)}`;
  return datesHidden ? null : "Hiked before Trekly";
}
