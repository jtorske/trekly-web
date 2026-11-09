import { apiFetch } from "./api";
import type { ActivityPage, ActivityScope } from "./activity";

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
