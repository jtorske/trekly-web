import { API_BASE, ApiError, apiFetch } from "./api";

export type NightStatus = "available" | "full" | "closed" | "not_released" | "unknown";
export type StaySummary = NightStatus | "partial";

export interface CampgroundAvailability {
  site_id: string;
  summary: StaySummary;
  nights: { date: string; status: NightStatus }[];
}

export interface TrailAvailability {
  trail_id: string;
  start: string;
  nights: number;
  party_size: number;
  checked_at: string | null;
  campgrounds: CampgroundAvailability[];
}

export interface Stay {
  start: string; // YYYY-MM-DD, first night
  nights: number;
  party: number;
}

export const MAX_NIGHTS = 14;
export const MAX_PARTY = 12;

/** On-demand check of a trail's campgrounds (no sign-in needed). */
export async function checkTrailAvailability(
  trailId: string,
  stay: Stay,
  signal?: AbortSignal,
): Promise<TrailAvailability> {
  const params = new URLSearchParams({
    start: stay.start,
    nights: String(stay.nights),
    party: String(stay.party),
  });
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/trails/${encodeURIComponent(trailId)}/availability?${params}`, { signal });
  } catch (error) {
    if ((error as { name?: string }).name === "AbortError") throw error;
    throw new ApiError("We couldn't reach Trekly. Check your connection and try again.", 0);
  }
  if (res.ok) return res.json();
  const body = await res.json().catch(() => null);
  const detail = typeof body?.detail === "string" ? body.detail : null;
  if (res.status === 429) {
    throw new ApiError(detail ?? "Lots of people are checking right now. Try again in a minute.", 429);
  }
  throw new ApiError(detail ?? "We couldn't check availability right now. Try again shortly.", res.status);
}

export type AlertStatus = "active" | "notified" | "cancelled" | "expired";

export interface CampgroundAlert {
  id: string;
  site_id: string;
  campground: string;
  site_code: string | null;
  park: string | null;
  trail: { id: string; name: string } | null;
  start_date: string;
  end_date: string;
  nights: number;
  party_size: number;
  status: AlertStatus;
  last_summary: StaySummary | null;
  last_checked_at: string | null;
  notified_at: string | null;
  created_at: string;
}

export interface NewAlert {
  site_id: string;
  trail_id: string | null;
  start_date: string;
  nights: number;
  party_size: number;
}

export const alertsApi = {
  list: (signal?: AbortSignal) => apiFetch<CampgroundAlert[]>("/api/me/alerts", { auth: true, signal }),
  create: (alert: NewAlert) => apiFetch<CampgroundAlert>("/api/me/alerts", { method: "POST", body: alert, auth: true }),
  cancel: (id: string) => apiFetch<CampgroundAlert>(`/api/me/alerts/${id}/cancel`, { method: "POST", auth: true }),
  rearm: (id: string) => apiFetch<CampgroundAlert>(`/api/me/alerts/${id}/rearm`, { method: "POST", auth: true }),
  remove: (id: string) => apiFetch<void>(`/api/me/alerts/${id}`, { method: "DELETE", auth: true }),
};
