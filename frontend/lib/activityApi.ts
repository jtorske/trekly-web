import { apiFetch } from "./api";
import type { ActivityPage, ActivityScope, HighFivers, ProfileActivityPage, TrendingTrail } from "./activity";

/** Signed in, the token is sent (for "high-fived", "yours" and the province); guests get the same posts. */
export const getActivity = (scope: ActivityScope, cursor: string | null, signedIn: boolean, signal?: AbortSignal) => {
  const query = new URLSearchParams({ scope });
  if (cursor) query.set("cursor", cursor);
  return apiFetch<ActivityPage>(`/api/activity?${query}`, { auth: signedIn, signal });
};

export const setHighFive = (postId: string, on: boolean) =>
  apiFetch<{ high_fives: number; high_fived: boolean }>(`/api/activity/${encodeURIComponent(postId)}/high-five`, {
    method: on ? "PUT" : "DELETE",
    auth: true,
  });

export const deleteActivityPost = (postId: string) =>
  apiFetch<void>(`/api/activity/${encodeURIComponent(postId)}`, { method: "DELETE", auth: true });

/** Who high-fived: public profiles by name, the rest as a count. */
export const getHighFivers = (postId: string, signedIn: boolean, signal?: AbortSignal) =>
  apiFetch<HighFivers>(`/api/activity/${encodeURIComponent(postId)}/high-fives`, { auth: signedIn, signal });

/** Most logged or saved this week, topped up with popular trails. */
export const getTrending = (signal?: AbortSignal) =>
  apiFetch<{ trails: TrendingTrail[] }>("/api/activity/trending", { signal });

const pageQuery = (cursor: string | null, limit?: number) => {
  const query = new URLSearchParams();
  if (cursor) query.set("cursor", cursor);
  if (limit) query.set("limit", String(limit));
  const text = query.toString();
  return text ? `?${text}` : "";
};

/** The signed-in user's own posts, all of them, shown to others or not. */
export const getMyActivity = (cursor: string | null, limit?: number, signal?: AbortSignal) =>
  apiFetch<ProfileActivityPage>(`/api/me/activity${pageQuery(cursor, limit)}`, { auth: true, signal });

/** A profile's Activity tab as visitors see it; a 404 when it isn't open to them. */
export const getProfileActivity = (
  username: string,
  cursor: string | null,
  signedIn: boolean,
  limit?: number,
  signal?: AbortSignal,
) =>
  apiFetch<ProfileActivityPage>(`/api/profiles/${encodeURIComponent(username)}/activity${pageQuery(cursor, limit)}`, {
    auth: signedIn,
    signal,
  });
