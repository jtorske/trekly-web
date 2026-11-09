/**
 * Pure helpers for the admin pages: the users table's URL state, labels and
 * the wording of each confirmation. Kept free of React so they're tested
 * with node --test (adminView.test.ts).
 */
import type { AuditEntry, SortDir, UserAction, UserFilter, UserSort, UsersQuery, Visibility } from "./adminApi.ts";

export const USER_SORTS: readonly UserSort[] = ["joined", "last_sign_in", "name", "username", "email", "hikes", "gear", "alerts"];
export const USER_FILTERS: readonly UserFilter[] = ["all", "public", "private", "hidden", "banned", "no_username"];
export const PER_PAGE = 25;

export const DEFAULT_USERS_QUERY: UsersQuery = { q: "", sort: "joined", dir: "desc", filter: "all", page: 1 };

/** Columns that read best biggest-first when you first click them. */
const DESC_FIRST: ReadonlySet<UserSort> = new Set(["joined", "last_sign_in", "hikes", "gear", "alerts"]);

/** Users-table state from the URL; anything unknown falls back to the default. */
export function parseUsersQuery(params: URLSearchParams): UsersQuery {
  const sort = params.get("sort") as UserSort;
  const dir = params.get("dir") as SortDir;
  const filter = params.get("filter") as UserFilter;
  const page = Number.parseInt(params.get("page") ?? "", 10);
  return {
    q: (params.get("q") ?? "").slice(0, 100),
    sort: USER_SORTS.includes(sort) ? sort : DEFAULT_USERS_QUERY.sort,
    dir: dir === "asc" || dir === "desc" ? dir : DEFAULT_USERS_QUERY.dir,
    filter: USER_FILTERS.includes(filter) ? filter : DEFAULT_USERS_QUERY.filter,
    page: Number.isFinite(page) && page >= 1 ? page : 1,
  };
}

/** The URL query for a users-table state, leaving out defaults ("" for none). */
export function usersQueryString(query: UsersQuery): string {
  const params = new URLSearchParams();
  if (query.q.trim()) params.set("q", query.q.trim());
  if (query.sort !== DEFAULT_USERS_QUERY.sort) params.set("sort", query.sort);
  if (query.dir !== DEFAULT_USERS_QUERY.dir) params.set("dir", query.dir);
  if (query.filter !== DEFAULT_USERS_QUERY.filter) params.set("filter", query.filter);
  if (query.page !== 1) params.set("page", String(query.page));
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Clicking a column header: flip it if it's already the sort, else start it in its natural direction. Back to page 1. */
export function nextSort(query: UsersQuery, column: UserSort): UsersQuery {
  if (query.sort === column) return { ...query, dir: query.dir === "asc" ? "desc" : "asc", page: 1 };
  return { ...query, sort: column, dir: DESC_FIRST.has(column) ? "desc" : "asc", page: 1 };
}

export function pageCount(total: number, perPage: number): number {
  return Math.max(1, Math.ceil(total / perPage));
}

export const VISIBILITY_LABELS: Record<Visibility, string> = {
  public: "Public",
  private: "Private",
  hidden: "Hidden by admin",
  no_username: "No username",
};

export const FILTER_LABELS: Record<UserFilter, string> = {
  all: "All",
  public: "Public",
  private: "Private",
  hidden: "Hidden",
  banned: "Banned",
  no_username: "No username",
};

const PROVIDER_LABELS: Record<string, string> = { email: "Email", google: "Google", apple: "Apple", github: "GitHub" };

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1);
}

export const ACTION_LABELS: Record<AuditEntry["action"], string> = {
  hide_profile: "Hid profile",
  unhide_profile: "Unhid profile",
  clear_username: "Cleared username",
  ban_user: "Banned",
  unban_user: "Unbanned",
  send_password_reset: "Sent password reset",
  resolve_report: "Resolved report",
  reopen_report: "Reopened report",
  hide_post: "Hid Activity post",
  unhide_post: "Unhid Activity post",
};

export interface Confirmation {
  title: string;
  body: string;
  confirm: string;
  /** Asks for an optional reason, kept in the audit log. */
  reason: boolean;
  danger: boolean;
}

/** What each account action's confirmation says, for the user it targets. */
export function confirmationFor(action: UserAction, who: string, email: string | null): Confirmation {
  switch (action) {
    case "hide":
      return { title: `Hide ${who}'s profile?`, body: "Their profile and trip notes become “not found” for everyone else. They're told it was hidden.", confirm: "Hide profile", reason: true, danger: true };
    case "unhide":
      return { title: `Show ${who}'s profile again?`, body: "Their profile goes back to following their own privacy settings.", confirm: "Unhide profile", reason: false, danger: false };
    case "clear-username":
      return { title: `Clear ${who}'s username?`, body: "Their profile address stops working, and the app asks them to choose a new username the next time they open it.", confirm: "Clear username", reason: true, danger: true };
    case "ban":
      return { title: `Ban ${who}?`, body: "They can't sign in or refresh a session. A session that's already open lasts until its token expires, up to an hour. Their data isn't deleted.", confirm: "Ban account", reason: true, danger: true };
    case "unban":
      return { title: `Unban ${who}?`, body: "They can sign in again.", confirm: "Unban account", reason: false, danger: false };
    case "password-reset":
      return { title: `Send ${who} a password reset?`, body: `Supabase emails a reset link to ${email ?? "their address"}. Their current password keeps working until they change it.`, confirm: "Send reset email", reason: false, danger: false };
  }
}

/** "@alice", else the display name, else the email, else a short id. */
export function whoLabel(person: { username: string | null; display_name?: string | null; email?: string | null; id: string }): string {
  if (person.username) return `@${person.username}`;
  return person.display_name || person.email || `user ${person.id.slice(0, 8)}`;
}

const DATE = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "short", day: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** "Nov 2, 2026", or "—" for none. Date-only strings ("2026-08-14") are read as that calendar day. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : DATE.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : DATE_TIME.format(date);
}

/** "just now", "5 min ago", "3 h ago", "2 days ago"; "—" for none. */
export function timeAgo(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return "—";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "—";
  const minutes = Math.round((now - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}
