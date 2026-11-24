import { apiFetch } from "./api";
import type { TrailListItem } from "./trailsApi";

/** Trekly Guide's API (backend app/routers/guide.py). Nothing here is stored. */

export type GuideDifficulty = "easier" | "similar" | "push";
export type GuideLength = "short" | "half_day" | "full_day" | "overnight";
export type GuideActivity = "hike" | "winter_hike" | "snowshoe" | "xc_ski";
export type GuideExperience = "new" | "few_seasons" | "seasoned";
export type Verdict = "ready" | "stretch" | "not_yet";

export interface RecommendRequest {
  /** ISO date or "this_weekend". */
  date?: string;
  difficulty?: GuideDifficulty;
  length?: GuideLength | null;
  province?: string | null;
  regions?: string[];
  dog?: boolean;
  activity?: GuideActivity;
  avoid_avalanche?: boolean | null;
  include_hiked?: boolean;
  exclude_ids?: string[];
  limit?: number;
  experience?: GuideExperience | null;
}

export interface Recommendation {
  trail: TrailListItem;
  reasons: string[];
  est_hours: number | null;
  est_label: string | null;
  score: number;
  avalanche_exposure: string;
  winter_activities: string[];
  dog_policy: string;
  /** Bringing a dog: the official leash rule, or "Check dog rules". */
  dog_note: string | null;
}

export interface RecommendResponse {
  date: string;
  winter: boolean;
  avoid_avalanche: boolean;
  results: Recommendation[];
  matching: number;
  notes: string[];
  basis: "history" | "stated";
}

export interface ReadinessReason {
  kind: string;
  level: Verdict | "info";
  text: string;
}

export interface Readiness {
  verdict: Verdict;
  label: string;
  date: string;
  reasons: ReadinessReason[];
  est_hours: number | null;
  est_label: string | null;
  gentle: boolean;
  build_up: TrailListItem[];
  avalanche_link: string | null;
  pace_factor: number;
  pace_confidence: "low" | "medium" | "high";
}

export interface HikerProfile {
  experience: {
    hike_count: number;
    max_distance_km: number;
    max_gain_m: number;
    typical_distance_km: number;
    typical_gain_m: number;
    basis: "history" | "stated";
  };
  pace: { factor: number; confidence: "low" | "medium" | "high"; timed_hikes: number };
  preferences: {
    hiking_style: string | null;
    experience_level: GuideExperience | null;
    favourite_regions: string[];
    scenery: string[];
    hikes_with_dog: boolean;
    use_history: boolean;
  };
  home_province: string | null;
}

export interface GuideSettings {
  use_history: boolean;
  hikes_with_dog: boolean;
  scenery: string[];
}

export const recommendTrails = (request: RecommendRequest, signedIn: boolean, signal?: AbortSignal) =>
  apiFetch<RecommendResponse>("/api/guide/recommend", { method: "POST", body: request, auth: signedIn, signal });

export const getReadiness = (slug: string, date: string | null, signal?: AbortSignal) =>
  apiFetch<Readiness>(
    `/api/guide/readiness/${encodeURIComponent(slug)}${date ? `?date=${encodeURIComponent(date)}` : ""}`,
    { auth: true, signal },
  );

export const getGuideProfile = (signal?: AbortSignal) =>
  apiFetch<HikerProfile>("/api/guide/profile", { auth: true, signal });

export const getGuideSettings = (signal?: AbortSignal) =>
  apiFetch<GuideSettings>("/api/me/guide-settings", { auth: true, signal });

export const updateGuideSettings = (update: Partial<GuideSettings>) =>
  apiFetch<GuideSettings>("/api/me/guide-settings", { method: "PATCH", body: update, auth: true });
