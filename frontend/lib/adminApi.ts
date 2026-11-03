import { apiFetch } from "./api";

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
  name: string;
}

export interface AdminReport {
  id: string;
  kind: "profile" | "trip_note";
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
}

export type AuditAction =
  | "hide_profile"
  | "unhide_profile"
  | "clear_username"
  | "ban_user"
  | "unban_user"
  | "send_password_reset"
  | "resolve_report"
  | "reopen_report";

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
  hikes_list: { id: string; trail: TrailRef; hiked_on: string; note: string | null; has_photo: boolean }[];
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
  audit: (page: number, perPage: number, signal?: AbortSignal) =>
    apiFetch<Page<AuditEntry>>(`${BASE}/audit?${query({ page, per_page: perPage })}`, { auth: true, signal }),
};
