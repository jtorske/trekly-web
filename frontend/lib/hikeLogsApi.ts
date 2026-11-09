import { apiFetch } from "./api";
import type { Tier } from "./milestones";
import type { TrailListItem } from "./trailsApi";

/** One Trail Journal entry: a trail the user has hiked. Private to them. */
export interface HikeLog {
  trail: TrailListItem;
  /** YYYY-MM-DD, a plain calendar date; null for a hike from before Trekly. */
  hiked_on: string | null;
  note: string | null;
  /** `{userId}/{uuid}.webp|jpg` in the private hike-photos bucket. */
  photo_path: string | null;
  /** Matched against a GPS track. */
  verified: boolean;
  /** The track's nights for an overnight trip; null means the trail's typical nights. */
  nights: number | null;
  logged_at: string;
  updated_at: string;
  /** Posted to the Activity feed. */
  shared: boolean;
}

export interface HikeLogInput {
  hiked_on: string | null;
  note: string | null;
  photo_path: string | null;
  /** "Share to Activity": true posts it, false removes its post, left out changes nothing. */
  share?: boolean;
}

export const HIKE_NOTE_MAX = 500;

/**
 * What new hikes changed, from one evaluation of the whole journal on the
 * server (app/hike_service.py): totals after, and what's new.
 */
export interface JournalProgress {
  /** Trails in the journal now. */
  stamps: number;
  new_stamps: number;
  /** Earned by these hikes, in journal order. */
  new_milestones: { id: string; category: string; title: string; tier: Tier | null; icon: string }[];
  milestones_earned: number;
  points: number;
  points_gained: number;
  rank: { level: number; title: string };
  ranked_up: boolean;
}

/** A saved entry; `progress` is set when it was new, null for an edit. */
export type SavedHikeLog = HikeLog & { progress: JournalProgress | null };

export const listHikeLogs = (signal?: AbortSignal) =>
  apiFetch<HikeLog[]>("/api/me/hike-logs", { auth: true, signal });

/** Creates the entry or replaces all of its fields. */
export const putHikeLog = (trailId: string, input: HikeLogInput) =>
  apiFetch<SavedHikeLog>(`/api/me/hike-logs/${encodeURIComponent(trailId)}`, {
    method: "PUT",
    body: input,
    auth: true,
  });

export interface PastHikesResult {
  added: HikeLog[];
  /** Already in the journal, or retired from the catalogue. */
  skipped: number;
  progress: JournalProgress;
}

/** Adds undated hikes from before Trekly; trails already logged keep their entry. */
export const addPastHikes = (trailIds: string[]) =>
  apiFetch<PastHikesResult>("/api/me/hike-logs/past", {
    method: "POST",
    body: { trail_ids: trailIds },
    auth: true,
  });

export const deleteHikeLog = (trailId: string) =>
  apiFetch<void>(`/api/me/hike-logs/${encodeURIComponent(trailId)}`, {
    method: "DELETE",
    auth: true,
  });
