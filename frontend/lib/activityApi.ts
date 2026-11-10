import { apiFetch } from "./api";
import type { ActivityPage, ActivityScope, HighFivers, TrendingTrail } from "./activity";

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
