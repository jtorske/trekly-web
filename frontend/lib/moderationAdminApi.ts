import { apiFetch } from "./api";
import type { Page, PersonRef, TrailRef } from "./adminApi";

/**
 * The admin moderation queue (/api/admin/moderation, app/routers/admin_moderation.py).
 * The backend checks the admin on every call and audits every action.
 */

export type ModerationView = "queue" | "held" | "hidden" | "all";
export type ModerationSort = "newest" | "most_reported";
export type ItemKind = "post" | "hike_note" | "hike_photo" | "bio" | "avatar" | "profile" | "comment";
export type QueueReason = "flagged" | "unscreened" | "reported" | "child_safety" | "edited_after_hide";

export interface ModerationReport {
  id: string;
  reason: string;
  details: string | null;
  reporter: PersonRef;
  /** Confirmed email, old enough account, not blocked by the author. */
  counts_toward_hide: boolean;
  status: "open" | "resolved";
  created_at: string;
}

export interface ModerationAuthor extends PersonRef {
  email_confirmed: boolean | null;
  joined: string | null;
  restriction: "locked" | "suspended" | null;
  suspended_until: string | null;
  previous_items: number;
}

export interface ModerationItem {
  id: string;
  kind: ItemKind;
  target_id: string;
  state: "visible" | "held" | "hidden";
  in_queue: boolean;
  queue_reason: QueueReason | null;
  child_safety: boolean;
  text: string | null;
  /** Short-lived link; never set for a child-safety item. */
  photo_url: string | null;
  has_photo: boolean;
  context: string | null;
  trail: TrailRef | null;
  screening: "passed" | "flagged" | "unavailable" | null;
  flagged_categories: string[];
  scores: { category: string; score: number }[];
  screened_at: string | null;
  open_reports: number;
  qualifying_reports: number;
  reports: ModerationReport[];
  author: ModerationAuthor;
  created_at: string;
  activity_at: string;
  decision: "approved" | "hidden" | null;
  decision_reason: string | null;
  decided_at: string | null;
  decided_by: PersonRef | null;
}

export interface ModerationPage extends Page<ModerationItem> {
  queue_total: number;
}

export const KIND_LABELS: Record<ItemKind, string> = {
  post: "Activity post",
  hike_note: "Hike note",
  hike_photo: "Hike photo",
  bio: "Bio",
  avatar: "Profile photo",
  profile: "Profile",
  comment: "Comment",
};

export const REASON_LABELS: Record<QueueReason, string> = {
  flagged: "Flagged by the check",
  unscreened: "Unscreened (check was down)",
  reported: "Reported",
  child_safety: "Child safety",
  edited_after_hide: "Edited after a hide",
};

const BASE = "/api/admin/moderation";
type Message = { ok: true; message: string };

export const moderationApi = {
  list: (view: ModerationView, sort: ModerationSort, page: number, perPage: number, signal?: AbortSignal) =>
    apiFetch<ModerationPage>(
      `${BASE}?${new URLSearchParams({ view, sort, page: String(page), per_page: String(perPage) })}`,
      { auth: true, signal },
    ),
  approve: (id: string) => apiFetch<Message>(`${BASE}/${encodeURIComponent(id)}/approve`, { method: "POST", auth: true }),
  hide: (id: string, reason: string) =>
    apiFetch<Message>(`${BASE}/${encodeURIComponent(id)}/hide`, { method: "POST", auth: true, body: { reason } }),
  warn: (userId: string, reason: string) =>
    apiFetch<Message>(`${BASE}/users/${encodeURIComponent(userId)}/warn`, { method: "POST", auth: true, body: { reason } }),
  suspend: (userId: string, days: number, reason: string) =>
    apiFetch<Message>(`${BASE}/users/${encodeURIComponent(userId)}/suspend`, {
      method: "POST",
      auth: true,
      body: { days, reason },
    }),
  ban: (userId: string, reason: string) =>
    apiFetch<Message>(`${BASE}/users/${encodeURIComponent(userId)}/ban`, { method: "POST", auth: true, body: { reason } }),
  unlock: (userId: string) =>
    apiFetch<Message>(`${BASE}/users/${encodeURIComponent(userId)}/unlock`, { method: "POST", auth: true }),
};
