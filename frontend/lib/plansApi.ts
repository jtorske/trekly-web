import { apiFetch } from "./api";
import type { GearSetup } from "./setupsApi";

/** campground: a site on the trail. undecided: not chosen yet. outside: somewhere Parks Canada doesn't book. */
export type NightChoice = "campground" | "undecided" | "outside";

/** Worked out by the API: booked > alert > last check > not checked. */
export type PlanNightStatus =
  | "booked"
  | "alert"
  | "available"
  | "full"
  | "closed"
  | "not_released"
  | "unknown"
  | "not_checked";

export interface PlanSite {
  id: string;
  name: string;
  site_code: string | null;
  stop_name: string | null;
  park: string | null;
  kind: string;
  max_group_size: number | null;
  retired: boolean;
  /** Parks Canada shows its availability online. */
  checkable: boolean;
  book_url: string | null;
}

export interface PlanNight {
  night_index: number;
  date: string; // YYYY-MM-DD, a plain calendar date
  choice: NightChoice;
  site: PlanSite | null;
  booked_by_me: boolean;
  /** Null for a night with no campground that isn't marked booked. */
  status: PlanNightStatus | null;
  alert_id: string | null;
  last_status: string | null;
  last_checked_at: string | null;
}

export interface PlanTrail {
  id: string;
  name: string;
  region: string;
  typical_duration_nights: number | null;
}

export interface TripPlanSummary {
  id: string;
  title: string | null;
  trail: PlanTrail;
  start_date: string;
  /** The morning you walk out. */
  end_date: string;
  last_night: string;
  nights: number;
  party_size: number;
  booked_nights: number;
  updated_at: string;
}

export interface TripPlan extends TripPlanSummary {
  notes: string | null;
  setup_id: string | null;
  setup: GearSetup | null;
  itinerary: PlanNight[];
  permits: { name: string; book_url: string | null }[];
  created_at: string;
}

export interface PlanInput {
  title: string | null;
  start_date: string;
  nights: number;
  party_size: number;
  setup_id: string | null;
  notes: string | null;
  itinerary: { choice: NightChoice; site_id: string | null }[];
  /** Needed when the edit would unmark a "booked by me" night. */
  confirm_drop_booked?: boolean;
}

const path = (id: string) => `/api/me/plans/${encodeURIComponent(id)}`;

export const plansApi = {
  list: (signal?: AbortSignal) => apiFetch<TripPlanSummary[]>("/api/me/plans", { auth: true, signal }),
  get: (id: string, signal?: AbortSignal) => apiFetch<TripPlan>(path(id), { auth: true, signal }),
  create: (trailId: string, input: PlanInput) =>
    apiFetch<TripPlan>("/api/me/plans", { method: "POST", body: { trail_id: trailId, ...input }, auth: true }),
  update: (id: string, input: PlanInput) => apiFetch<TripPlan>(path(id), { method: "PUT", body: input, auth: true }),
  setBooked: (id: string, nightIndex: number, booked: boolean) =>
    apiFetch<TripPlan>(`${path(id)}/nights/${nightIndex}`, {
      method: "PUT",
      body: { booked_by_me: booked },
      auth: true,
    }),
  check: (id: string) => apiFetch<TripPlan>(`${path(id)}/check`, { method: "POST", auth: true }),
  remove: (id: string) => apiFetch<void>(path(id), { method: "DELETE", auth: true }),
};
