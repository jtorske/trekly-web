import { apiFetch } from "./api";
import type { FollowList, FollowState, PeoplePage, Person } from "./follows";

const enc = encodeURIComponent;

export const setFollow = (username: string, on: boolean) =>
  apiFetch<{ follow: FollowState; followers_count: number }>(`/api/profiles/${enc(username)}/follow`, {
    method: on ? "PUT" : "DELETE",
    auth: true,
  });

export function getFollowList(
  username: string,
  which: FollowList,
  { q, cursor, signedIn, signal }: { q?: string; cursor?: string | null; signedIn: boolean; signal?: AbortSignal },
) {
  const query = new URLSearchParams();
  if (q?.trim()) query.set("q", q.trim());
  if (cursor) query.set("cursor", cursor);
  const suffix = query.size ? `?${query}` : "";
  return apiFetch<PeoplePage>(`/api/profiles/${enc(username)}/${which}${suffix}`, { auth: signedIn, signal });
}

export function getFollowRequests({ q, cursor, signal }: { q?: string; cursor?: string | null; signal?: AbortSignal } = {}) {
  const query = new URLSearchParams();
  if (q?.trim()) query.set("q", q.trim());
  if (cursor) query.set("cursor", cursor);
  const suffix = query.size ? `?${query}` : "";
  return apiFetch<PeoplePage>(`/api/me/follow-requests${suffix}`, { auth: true, signal });
}

export const approveFollowRequest = (username: string) =>
  apiFetch<Person>(`/api/me/follow-requests/${enc(username)}`, { method: "POST", auth: true });

export const declineFollowRequest = (username: string) =>
  apiFetch<void>(`/api/me/follow-requests/${enc(username)}`, { method: "DELETE", auth: true });

export const removeFollower = (username: string) =>
  apiFetch<void>(`/api/me/followers/${enc(username)}`, { method: "DELETE", auth: true });
