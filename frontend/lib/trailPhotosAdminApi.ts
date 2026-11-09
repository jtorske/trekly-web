import { API_BASE, ApiError, apiFetch } from "./api";
import { getSupabaseClient } from "./supabaseClient";
import type { TrailListItem, TrailPhoto } from "./trailsApi";

/**
 * Trail photo review (photo admins only). The backend checks
 * PHOTO_ADMIN_USER_IDS on every call; the page only hides itself.
 */
export type Confidence = "high" | "medium" | "low" | "off_topic";

export interface PhotoCandidate {
  id: string;
  source: "commons" | "openverse";
  origin: string | null;
  confidence: Confidence;
  title: string;
  preview_url: string;
  image_url: string;
  width: number;
  height: number;
  photographer: string;
  license: string;
  license_url: string | null;
  source_url: string;
  distance_m: number | null;
  /** What distance_m is measured from: the stored route, or the trailhead (older searches). */
  distance_from?: "route" | "trailhead";
  /** Why it got its confidence: "Names Brazeau Lake", "0.4 km from the route". */
  match?: string | null;
  /** Below the 1600px search minimum (found by the 1024px fallback). */
  low_res: boolean;
}

export interface ReviewTrail {
  trail: TrailListItem;
  destination: string | null;
  best_confidence: Confidence | null;
  /** Preselected candidate; null starts the trail on the topo fallback. */
  default_choice: string | null;
  candidates: PhotoCandidate[];
  /** When these candidates were loaded; newer than review.reviewed_at means "To review". */
  candidates_loaded_at: string | null;
  review: {
    decision: "approved" | "rejected" | "uploaded";
    candidate_id: string | null;
    reviewed_at?: string | null;
  } | null;
}

const BASE = "/api/admin/trail-photos";

export const trailPhotosAdminApi = {
  isAdmin: () => apiFetch<{ admin: true }>(`${BASE}/me`, { auth: true }),
  list: () => apiFetch<ReviewTrail[]>(BASE, { auth: true }),
  approve: (trailId: string, candidateId: string) =>
    apiFetch<TrailPhoto>(`${BASE}/${trailId}/approve`, { method: "POST", auth: true, body: { candidate_id: candidateId } }),
  reject: (trailId: string) => apiFetch<void>(`${BASE}/${trailId}/reject`, { method: "POST", auth: true }),
  removePhoto: (trailId: string) => apiFetch<void>(`${BASE}/${trailId}/photo`, { method: "DELETE", auth: true }),

  /** Your own photo as the raw request body; the server resizes it and credits your profile name. */
  async upload(trailId: string, file: File): Promise<TrailPhoto> {
    const { data } = await getSupabaseClient().auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new ApiError("Sign in to continue.", 401);
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${BASE}/${trailId}/upload`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": file.type },
        body: file,
      });
    } catch {
      throw new ApiError("We couldn't reach Trekly. Check your connection and try again.", 0);
    }
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = (payload as { detail?: unknown } | null)?.detail;
      throw new ApiError(typeof detail === "string" ? detail : "The upload didn't work. Try again.", response.status);
    }
    return payload as TrailPhoto;
  },
};

/**
 * Strong: names the trail or a landmark on it, or taken within 1 km of the
 * route. Likely: within 3 km. Weak: park or region match only (and the
 * first search's Openverse keyword matches).
 */
export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  high: "Strong",
  medium: "Likely",
  low: "Weak",
  off_topic: "Weak",
};
