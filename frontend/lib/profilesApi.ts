import { apiFetch } from "./api";
import type { FeaturedBadge } from "./featuredBadges";
import type { GearItem } from "./gearApi";
import type { TrailListItem } from "./trailsApi";
import type { MilestoneBadgeInfo } from "./milestones";
import type { ProvinceCode } from "./provinces";

/**
 * Public profiles (/u/[username]) and the owner's privacy settings.
 *
 * The API returns the same visitor view to everyone, the owner included, and
 * leaves out every hidden section: nothing here is hidden by the client. Row-
 * level security applies the same settings to direct Supabase access (photo
 * signed URLs), so a visitor can only sign photos from public sections.
 */

export interface PrivacySettings {
  is_private: boolean;
  show_journal: boolean;
  show_rank: boolean;
  show_gear: boolean;
  show_saved_trails: boolean;
  show_trip_plans: boolean;
  hide_hike_dates: boolean;
  allow_search_indexing: boolean;
  /** "Show me in community features": "Hiked by" on trail pages. In effect only while the journal is public. */
  show_in_community: boolean;
  /** "Home province": visitors see the home province (and its badge). Off until turned on. */
  show_home_province: boolean;
  /** "Visit streak": visitors see the current and best streak. Off until turned on. */
  show_visit_streak: boolean;
  /** The one-time "profiles can be public now" banner, for existing users. */
  public_notice_pending: boolean;
  username: string | null;
  hidden_by_moderators: boolean;
}

export type PrivacyUpdate = Partial<Omit<PrivacySettings, "username" | "hidden_by_moderators" | "public_notice_pending">> & {
  public_notice_pending?: false;
};

export type PublicGearItem = Pick<
  GearItem,
  "id" | "kind" | "display_name" | "brand_name" | "category" | "product" | "variant" | "custom_brand" | "custom_model" | "quantity" | "weight" | "capacity"
>;

export interface PublicSetup {
  id: string;
  name: string;
  description: string | null;
  items: PublicGearItem[];
  item_count: number;
  known_weight_g: number;
  items_missing_weight: number;
}

export interface PublicJournalEntry {
  trail: TrailListItem;
  /** null when the owner hides the dates of their hikes. */
  hiked_on: string | null;
  note: string | null;
  photo_path: string | null;
}

export interface PublicTripPlan {
  id: string;
  trail: TrailListItem;
  title: string | null;
  start_date: string;
  nights: number;
}

export interface PublicProfile {
  username: string;
  display_name: string | null;
  avatar_path: string | null;
  is_private: boolean;
  allow_indexing: boolean;
  /** Each of these is null when the profile is private or the section is hidden. */
  bio: string | null;
  /** Only while the owner has "Home province" switched on. */
  home_province: ProvinceCode | null;
  rank: { level: number; title: string } | null;
  /** Only while the owner has "Visit streak" switched on; current is 0 once lapsed. */
  visit_streak: { current: number; longest: number } | null;
  /** `milestones`: earned ones only (seasonal ones left out while dates are hidden). */
  journal: { hide_dates: boolean; entries: PublicJournalEntry[]; milestones: MilestoneBadgeInfo[] } | null;
  /** Shown with the Trail Journal (same switch); the owner's picks or their latest badges. */
  featured_badges: FeaturedBadge[] | null;
  gear: { items: PublicGearItem[]; setups: PublicSetup[] } | null;
  saved_trails: TrailListItem[] | null;
  trip_plans: PublicTripPlan[] | null;
}

export const REPORT_REASONS = [
  { value: "spam", label: "Spam or advertising" },
  { value: "harassment", label: "Harassment or hate" },
  { value: "inappropriate", label: "Inappropriate photos or text" },
  { value: "impersonation", label: "Pretending to be someone else" },
  { value: "privacy", label: "Shares someone else's private information" },
  { value: "other", label: "Something else" },
] as const;

export type ReportReason = (typeof REPORT_REASONS)[number]["value"];

export const getPrivacy = (signal?: AbortSignal) =>
  apiFetch<PrivacySettings>("/api/me/privacy", { auth: true, signal });

const PRIVACY_EVENT = "trekly:privacy-updated";

/** Saves a change and tells every listener (e.g. the corner notice) the new settings. */
export async function updatePrivacy(update: PrivacyUpdate): Promise<PrivacySettings> {
  const saved = await apiFetch<PrivacySettings>("/api/me/privacy", { method: "PATCH", body: update, auth: true });
  window.dispatchEvent(new CustomEvent<PrivacySettings>(PRIVACY_EVENT, { detail: saved }));
  return saved;
}

export function onPrivacyUpdated(listener: (settings: PrivacySettings) => void): () => void {
  const handler = (event: Event) => listener((event as CustomEvent<PrivacySettings>).detail);
  window.addEventListener(PRIVACY_EVENT, handler);
  return () => window.removeEventListener(PRIVACY_EVENT, handler);
}

export const getPublicProfile = (username: string, signal?: AbortSignal) =>
  apiFetch<PublicProfile>(`/api/profiles/${encodeURIComponent(username)}`, { signal });

/** Reports a profile, or with `trailId`, their trip note on that trail. */
export const reportProfile = (username: string, reason: ReportReason, details: string, trailId?: string) =>
  apiFetch<{ status: string }>(`/api/profiles/${encodeURIComponent(username)}/report`, {
    method: "POST",
    body: { reason, details: details.trim() || null, ...(trailId ? { trail_id: trailId } : {}) },
    auth: true,
  });

/** The fields GearList and GearThumb need, filled in for a visitor's read-only view. */
export function asGearItem(item: PublicGearItem): GearItem {
  return {
    ...item,
    custom_name: null,
    custom_specs: [],
    notes: null,
    condition: null,
    image_path: null,
    carry: null,
    mat_slot: null,
    created_at: "",
    updated_at: "",
  } as GearItem;
}

export function publicProfilePath(username: string): string {
  return `/u/${encodeURIComponent(username)}`;
}
