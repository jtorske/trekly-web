import { apiFetch } from "./api";
import type { TrailListItem } from "./trailsApi";
import type { UnitSystem } from "./units";

export interface Profile {
  id: string;
  email: string | null;
  display_name: string | null;
  username: string | null;
  bio: string | null;
  home_region: string | null;
  avatar_path: string | null;
  /** Display units; null until the user picks, which reads as metric. */
  units: UnitSystem | null;
  member_since: string | null;
  counts: { saved_trails: number; gear_items: number };
  /** "public" once there's a username and the profile isn't set to private. */
  visibility: "public" | "private";
}

export type ProfileUpdate = Partial<
  Pick<Profile, "display_name" | "username" | "bio" | "home_region" | "avatar_path" | "units">
>;

export interface SavedTrail {
  trail: TrailListItem;
  saved_at: string;
}

export const getProfile = (signal?: AbortSignal) =>
  apiFetch<Profile>("/api/me/profile", { auth: true, signal });

export const updateProfile = (update: ProfileUpdate) =>
  apiFetch<Profile>("/api/me/profile", { method: "PATCH", body: update, auth: true });

export const listSavedTrails = (signal?: AbortSignal) =>
  apiFetch<SavedTrail[]>("/api/me/saved-trails", { auth: true, signal });

export const saveTrail = (trailId: string) =>
  apiFetch<SavedTrail>(`/api/me/saved-trails/${encodeURIComponent(trailId)}`, {
    method: "PUT",
    auth: true,
  });

export const unsaveTrail = (trailId: string) =>
  apiFetch<void>(`/api/me/saved-trails/${encodeURIComponent(trailId)}`, {
    method: "DELETE",
    auth: true,
  });

export interface UsernameCheck {
  username: string;
  available: boolean;
  message: string;
}

/** Whether a username is free and allowed. Open to guests (sign-up asks before there's a session). */
export const checkUsername = (username: string, signal?: AbortSignal) =>
  apiFetch<UsernameCheck>(`/api/usernames/check?username=${encodeURIComponent(username)}`, { signal });

/** A free username based on a display name or email, e.g. jordan_torske or jordan_torske2. */
export const suggestUsername = (hint: string, signal?: AbortSignal) =>
  apiFetch<{ username: string }>(`/api/usernames/suggest?hint=${encodeURIComponent(hint)}`, { signal });

export const DELETE_CONFIRMATION = "delete my account";

export const deleteAccount = (confirm: string) =>
  apiFetch<void>("/api/me", { method: "DELETE", body: { confirm }, auth: true });
