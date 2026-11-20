import { apiFetch } from "./api";
import type { ActivityComment, ActivityPage, ActivityPost, CommentList, HighFivers, ProfileActivityPage, TrendingTrail } from "./activity";

/** One page of the blended feed. Signed in, the token is sent (who you follow, your trails, "high-fived"). */
export const getActivity = (cursor: string | null, signedIn: boolean, signal?: AbortSignal) => {
  const query = cursor ? `?${new URLSearchParams({ cursor })}` : "";
  return apiFetch<ActivityPage>(`/api/activity${query}`, { auth: signedIn, signal });
};

/** How many posts from people you follow arrived since the feed's `as_of`. */
export const getNewPosts = (since: string, signal?: AbortSignal) =>
  apiFetch<{ count: number }>(`/api/activity/new?${new URLSearchParams({ since })}`, { auth: true, signal });

export const setHighFive = (postId: string, on: boolean) =>
  apiFetch<{ high_fives: number; high_fived: boolean }>(`/api/activity/${encodeURIComponent(postId)}/high-five`, {
    method: on ? "PUT" : "DELETE",
    auth: true,
  });

/** The one-time "Share your past hikes?" prompt's answer; resolves to how many hikes were shared. */
export const answerPastHikes = (share: boolean) =>
  apiFetch<{ shared: number }>("/api/me/activity/past-hikes", { method: "POST", body: { share }, auth: true });

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

// ------------------------------------------------------------ comments

export const getPost = (postId: string, signedIn: boolean, signal?: AbortSignal) =>
  apiFetch<ActivityPost>(`/api/activity/${encodeURIComponent(postId)}`, { auth: signedIn, signal });

export const getComments = (postId: string, signedIn: boolean, signal?: AbortSignal) =>
  apiFetch<CommentList>(`/api/activity/${encodeURIComponent(postId)}/comments`, { auth: signedIn, signal });

export const addComment = (postId: string, body: string, parentId?: string | null) =>
  apiFetch<ActivityComment>(`/api/activity/${encodeURIComponent(postId)}/comments`, {
    method: "POST",
    body: parentId ? { body, parent_id: parentId } : { body },
    auth: true,
  });

export const editComment = (commentId: string, body: string) =>
  apiFetch<ActivityComment>(`/api/comments/${encodeURIComponent(commentId)}`, {
    method: "PATCH",
    body: { body },
    auth: true,
  });

export const deleteComment = (commentId: string) =>
  apiFetch<void>(`/api/comments/${encodeURIComponent(commentId)}`, { method: "DELETE", auth: true });

export const setCommentsOff = (postId: string, off: boolean) =>
  apiFetch<{ comments_off: boolean }>(`/api/activity/${encodeURIComponent(postId)}/comments-off`, {
    method: "PUT",
    body: { off },
    auth: true,
  });
