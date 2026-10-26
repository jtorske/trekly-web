import { apiFetch } from "./api";
import type { TrailListItem } from "./trailsApi";

/** One Trail Journal entry: a trail the user has hiked. Private to them. */
export interface HikeLog {
  trail: TrailListItem;
  /** YYYY-MM-DD, a plain calendar date. */
  hiked_on: string;
  note: string | null;
  /** `{userId}/{uuid}.webp|jpg` in the private hike-photos bucket. */
  photo_path: string | null;
  logged_at: string;
  updated_at: string;
}

export interface HikeLogInput {
  hiked_on: string;
  note: string | null;
  photo_path: string | null;
}

export const HIKE_NOTE_MAX = 500;

export const listHikeLogs = (signal?: AbortSignal) =>
  apiFetch<HikeLog[]>("/api/me/hike-logs", { auth: true, signal });

/** Creates the entry or replaces all of its fields. */
export const putHikeLog = (trailId: string, input: HikeLogInput) =>
  apiFetch<HikeLog>(`/api/me/hike-logs/${encodeURIComponent(trailId)}`, {
    method: "PUT",
    body: input,
    auth: true,
  });

export const deleteHikeLog = (trailId: string) =>
  apiFetch<void>(`/api/me/hike-logs/${encodeURIComponent(trailId)}`, {
    method: "DELETE",
    auth: true,
  });
