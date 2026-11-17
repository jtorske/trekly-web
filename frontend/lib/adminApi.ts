import type { AccountLabel } from "./accountLabels";
import { API_BASE, ApiError, apiFetch } from "./api";
import { getSupabaseClient } from "./supabaseClient";
import type { TrailListItem } from "./trailsApi";

/**
 * The admin area's API (/api/admin/...). The backend checks ADMIN_USER_IDS on
 * every call and answers 403 to anyone else; these pages only hide
 * themselves. Account actions run on the server with Supabase's service-role
 * key, which never reaches the browser: this file only ever sends the
 * signed-in admin's own access token.
 */

export type Visibility = "public" | "private" | "hidden" | "no_username";
export type UserSort = "joined" | "last_sign_in" | "name" | "username" | "email" | "hikes" | "gear" | "alerts";
export type UserFilter = "all" | "public" | "private" | "hidden" | "banned" | "no_username";
export type SortDir = "asc" | "desc";
export type ReportStatus = "open" | "resolved";

export interface AdminUser {
  id: string;
  email: string | null;
  display_name: string | null;
  username: string | null;
  avatar_path: string | null;
  providers: string[];
  joined_at: string | null;
  last_sign_in_at: string | null;
  hikes: number;
  gear: number;
  alerts: number;
  visibility: Visibility;
  banned: boolean;
  is_admin: boolean;
  /** "official" (the Trekly account) or "demo"; left out of the overview's numbers. */
  label?: AccountLabel | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface PersonRef {
  id: string;
  username: string | null;
  display_name: string | null;
}

export interface TrailRef {
  id: string;
  slug: string;
  name: string;
}

/** A reported Activity post, as it reads now. */
export interface ReportPost {
  id: string;
  kind: "hike" | "milestone" | "rank";
  /** e.g. "Hiked Skyline Trail", "Earned Park hopper", "Reached Ridge Walker". */
  summary: string;
  trail: TrailRef | null;
  note: string | null;
  has_photo: boolean;
  hidden: boolean;
  hidden_reason: string | null;
}

export interface AdminReport {
  id: string;
  kind: "profile" | "trip_note" | "post";
  status: ReportStatus;
  reason: string;
  details: string | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by: PersonRef | null;
  reported: PersonRef;
  reported_hidden: boolean;
  reporter: PersonRef;
  trail: TrailRef | null;
  note: string | null;
  /** A post report's post; null once its owner deleted it. */
  post?: ReportPost | null;
}

export type AuditAction =
  | "hide_profile"
  | "unhide_profile"
  | "clear_username"
  | "ban_user"
  | "unban_user"
  | "send_password_reset"
  | "resolve_report"
  | "reopen_report"
  | "hide_post"
  | "unhide_post"
  | "official_post"
  | "delete_official_post"
  | "approve_item"
  | "hide_item"
  | "warn_user"
  | "suspend_user"
  | "unsuspend_user"
  | "lock_account";

export interface AuditEntry {
  id: string;
  action: AuditAction;
  admin: PersonRef;
  target_user: PersonRef | null;
  target_report_id: string | null;
  details: Record<string, string>;
  created_at: string;
}

export interface AdminUserDetail extends AdminUser {
  bio: string | null;
  home_region: string | null;
  hidden_at: string | null;
  hidden_reason: string | null;
  banned_until: string | null;
  hikes_list: { id: string; trail: TrailRef; hiked_on: string | null; note: string | null; has_photo: boolean; verified: boolean }[];
  alerts_list: {
    id: string;
    site_name: string;
    trail: TrailRef | null;
    start_date: string;
    nights: number;
    party_size: number;
    status: string;
    created_at: string;
  }[];
  reports_about: AdminReport[];
  reports_filed: number;
  audit: AuditEntry[];
}

export interface Overview {
  users_total: number;
  signups_by_week: { week_start: string; count: number }[];
  hikes_total: number;
  active_alerts: number;
  open_reports: number;
  /** Held, reported and unscreened items waiting in /admin/moderation. */
  moderation_queue: number;
  poller: { last_started_at: string | null; last_finished_at: string | null; last_result: string | null; running: boolean } | null;
}

export interface UsersQuery {
  q: string;
  sort: UserSort;
  dir: SortDir;
  filter: UserFilter;
  page: number;
}

export type UserAction = "hide" | "unhide" | "clear-username" | "ban" | "unban" | "password-reset";

const BASE = "/api/admin";

function query(params: Record<string, string | number>): string {
  return new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
}

export const adminApi = {
  me: (signal?: AbortSignal) => apiFetch<{ admin: true }>(`${BASE}/me`, { auth: true, signal }),
  overview: (signal?: AbortSignal) => apiFetch<Overview>(`${BASE}/overview`, { auth: true, signal }),
  users: (q: UsersQuery, perPage: number, signal?: AbortSignal) =>
    apiFetch<Page<AdminUser>>(
      `${BASE}/users?${query({ q: q.q, sort: q.sort, dir: q.dir, filter: q.filter, page: q.page, per_page: perPage })}`,
      { auth: true, signal },
    ),
  user: (id: string, signal?: AbortSignal) =>
    apiFetch<AdminUserDetail>(`${BASE}/users/${encodeURIComponent(id)}`, { auth: true, signal }),
  act: (id: string, action: UserAction, reason?: string) =>
    apiFetch<{ ok: true; message: string }>(`${BASE}/users/${encodeURIComponent(id)}/${action}`, {
      method: "POST",
      auth: true,
      body: action === "hide" || action === "ban" || action === "clear-username" ? { reason: reason || null } : undefined,
    }),
  reports: (status: ReportStatus | "all", page: number, perPage: number, signal?: AbortSignal) =>
    apiFetch<Page<AdminReport>>(`${BASE}/reports?${query({ status, page, per_page: perPage })}`, { auth: true, signal }),
  setReportStatus: (id: string, status: ReportStatus) =>
    apiFetch<AdminReport>(`${BASE}/reports/${encodeURIComponent(id)}`, { method: "PATCH", auth: true, body: { status } }),
  setPostHidden: (postId: string, hidden: boolean, reason?: string) =>
    apiFetch<{ ok: true; message: string }>(
      `${BASE}/activity/${encodeURIComponent(postId)}/${hidden ? "hide" : "unhide"}`,
      { method: "POST", auth: true, body: hidden ? { reason: reason || null } : undefined },
    ),
  audit: (page: number, perPage: number, signal?: AbortSignal) =>
    apiFetch<Page<AuditEntry>>(`${BASE}/audit?${query({ page, per_page: perPage })}`, { auth: true, signal }),
};

/** Posting as the official @trekly account (/admin/posts). */
export interface OfficialPost {
  id: string;
  body: string;
  trail: TrailListItem | null;
  photo_url: string | null;
  created_at: string;
  hidden: boolean;
}

export interface OfficialPosts {
  /** null until backend/scripts/official_account.py has made the account. */
  account: { username: string; display_name: string | null; avatar_path: string | null } | null;
  posts: OfficialPost[];
}

export interface OfficialPhoto {
  photo_path: string;
  photo_url: string;
  width: number;
  height: number;
}

const OFFICIAL = "/api/admin/official-posts";

export const officialPostsApi = {
  list: (signal?: AbortSignal) => apiFetch<OfficialPosts>(OFFICIAL, { auth: true, signal }),
  create: (body: { body: string; trail_id: string | null; photo_path: string | null }) =>
    apiFetch<OfficialPost>(OFFICIAL, { method: "POST", auth: true, body }),
  remove: (id: string) => apiFetch<void>(`${OFFICIAL}/${encodeURIComponent(id)}`, { method: "DELETE", auth: true }),
  discardPhoto: (path: string) =>
    apiFetch<void>(`${OFFICIAL}/photo?${new URLSearchParams({ path })}`, { method: "DELETE", auth: true }),
  /** The photo as the raw request body; the server re-encodes it (no metadata) and stores it. */
  async uploadPhoto(file: File): Promise<OfficialPhoto> {
    const { data } = await getSupabaseClient().auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new ApiError("Sign in to continue.", 401);
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${OFFICIAL}/photo`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": file.type },
        body: file,
      });
    } catch {
      throw new ApiError("We couldn't reach Trekly. Check your connection and try again.", 0);
    }
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = (payload as { detail?: unknown } | null)?.detail;
      throw new ApiError(typeof detail === "string" ? detail : "The upload didn't work. Try again.", response.status);
    }
    return payload as OfficialPhoto;
  },
};

/** The review queue for automatic @trekly posts (/admin/trekly-posts). */
export type TreklyPostType = "trending" | "spotlight" | "new_on_trekly" | "roundup" | "fun_fact" | "conditions";
export type TreklyDraftStatus = "draft" | "scheduled" | "published" | "rejected" | "expired";
export type TreklyQueueFilter = "waiting" | "published" | "closed";

export interface TreklyPostTypeInfo {
  post_type: TreklyPostType;
  label: string;
  /** From backend/config/trekly_posts.toml. */
  enabled: boolean;
  days: string[];
  ai: boolean;
  /** On by default (the config); turned off here, drafts wait for an admin. */
  auto_publish: boolean;
}

export interface TreklyDraft {
  id: string;
  post_type: TreklyPostType;
  status: TreklyDraftStatus;
  body: string;
  template_body: string;
  /** "template", "ai" (passed the fact check) or "admin" (edited here). */
  writer: "template" | "ai" | "admin";
  /** Why the AI text wasn't used, when it was tried. */
  ai_note: string | null;
  trail: TrailListItem | null;
  source_url: string | null;
  source_label: string | null;
  source_date: string | null;
  data: Record<string, unknown>;
  run_date: string;
  publish_on: string | null;
  published_at: string | null;
  post_id: string | null;
  created_at: string;
  /** Why "Publish now" would be refused right now. */
  blocked: string | null;
}

export interface TreklyQueue {
  account: { username: string; display_name: string | null; avatar_path: string | null } | null;
  /** The local (Alberta) date the pacing rules use. */
  today: string;
  posts_today: number;
  max_posts_per_day: number;
  busy: boolean;
  types: TreklyPostTypeInfo[];
  counts: Record<TreklyDraftStatus, number>;
  drafts: TreklyDraft[];
}

export interface TreklyFact {
  id: string;
  text: string;
  trail: TrailListItem | null;
  park_name: string | null;
  source_url: string;
  approved: boolean;
  created_at: string;
  updated_at: string;
}

export interface TreklyFactInput {
  text: string;
  source_url: string;
  trail_id: string | null;
  park_name: string | null;
  approved?: boolean;
}

const TREKLY = "/api/admin/trekly-posts";
const draftUrl = (id: string, action = "") => `${TREKLY}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;

export const treklyPostsApi = {
  queue: (status: TreklyQueueFilter, signal?: AbortSignal) =>
    apiFetch<TreklyQueue>(`${TREKLY}?${query({ status })}`, { auth: true, signal }),
  edit: (id: string, body: string) => apiFetch<TreklyDraft>(draftUrl(id), { method: "PATCH", auth: true, body: { body } }),
  /** null takes it back to a plain draft. */
  schedule: (id: string, publishOn: string | null) =>
    apiFetch<TreklyDraft>(draftUrl(id, "schedule"), { method: "POST", auth: true, body: { publish_on: publishOn } }),
  publish: (id: string) => apiFetch<TreklyDraft>(draftUrl(id, "publish"), { method: "POST", auth: true }),
  reject: (id: string) => apiFetch<TreklyDraft>(draftUrl(id, "reject"), { method: "POST", auth: true }),
  setAutoPublish: (type: TreklyPostType, autoPublish: boolean) =>
    apiFetch<TreklyPostTypeInfo>(`${TREKLY}/types/${type}`, {
      method: "PUT",
      auth: true,
      body: { auto_publish: autoPublish },
    }),
  facts: (signal?: AbortSignal) => apiFetch<TreklyFact[]>(`${TREKLY}/facts`, { auth: true, signal }),
  createFact: (fact: TreklyFactInput) => apiFetch<TreklyFact>(`${TREKLY}/facts`, { method: "POST", auth: true, body: fact }),
  updateFact: (id: string, change: Partial<TreklyFactInput>) =>
    apiFetch<TreklyFact>(`${TREKLY}/facts/${encodeURIComponent(id)}`, { method: "PATCH", auth: true, body: change }),
  removeFact: (id: string) =>
    apiFetch<void>(`${TREKLY}/facts/${encodeURIComponent(id)}`, { method: "DELETE", auth: true }),
};
