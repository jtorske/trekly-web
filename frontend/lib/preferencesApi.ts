import { apiFetch } from "./api";
import type { Experience, HikingStyle, StepKey } from "./onboarding";
import type { TrailListItem } from "./trailsApi";

/**
 * Private trail preferences and /welcome progress. Only the owner can read
 * them (the API and row-level security both enforce it); they're used to
 * pick trails, never shown to visitors.
 */
export interface Preferences {
  hiking_style: HikingStyle | null;
  experience: Experience | null;
  favourite_regions: string[];
  onboarding: { step: StepKey | null; status: "completed" | "skipped" | null; finished_at: string | null };
}

export type PreferencesUpdate = Partial<Pick<Preferences, "hiking_style" | "experience" | "favourite_regions">> & {
  onboarding_step?: StepKey;
  onboarding_status?: "completed" | "skipped";
};

const PREFERENCES_EVENT = "trekly:preferences-updated";

export const getPreferences = (signal?: AbortSignal) =>
  apiFetch<Preferences>("/api/me/preferences", { auth: true, signal });

/** Saves a change and tells every listener (e.g. Explore's chips) the new answers. */
export async function updatePreferences(update: PreferencesUpdate): Promise<Preferences> {
  const saved = await apiFetch<Preferences>("/api/me/preferences", { method: "PATCH", body: update, auth: true });
  window.dispatchEvent(new CustomEvent<Preferences>(PREFERENCES_EVENT, { detail: saved }));
  return saved;
}

export function onPreferencesUpdated(listener: (preferences: Preferences) => void): () => void {
  const handler = (event: Event) => listener((event as CustomEvent<Preferences>).detail);
  window.addEventListener(PREFERENCES_EVENT, handler);
  return () => window.removeEventListener(PREFERENCES_EVENT, handler);
}

/** Trails picked from the answers and home province, best first, leaving out saved ones. */
export const getRecommendations = (limit = 5, signal?: AbortSignal) =>
  apiFetch<TrailListItem[]>(`/api/me/recommendations?limit=${limit}`, { auth: true, signal });
