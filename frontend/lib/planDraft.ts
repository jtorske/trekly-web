/**
 * Rules for the "Plan this trip" dialog and the plan pages: the starting
 * itinerary, resizing it, which edits would unmark booked nights, how a
 * guest's draft survives sign-in, and when a plan counts as past. Dates are
 * plain YYYY-MM-DD strings (see stay.ts), so no time zone can shift a night.
 */

import type { CampgroundAvailability, Stay } from "./availabilityApi";
import type { NightChoice, PlanNight, PlanNightStatus, TripPlan, TripPlanSummary } from "./plansApi";
import type { TrailCampground } from "./trailsApi";

export interface DraftNight {
  choice: NightChoice;
  siteId: string | null;
}

export const UNDECIDED: DraftNight = { choice: "undecided", siteId: null };
export const OUTSIDE: DraftNight = { choice: "outside", siteId: null };

/** Campgrounds a night can be spent at, in route order: never a trail permit. */
export function sleepableSites(campgrounds: TrailCampground[]): TrailCampground[] {
  return campgrounds.filter((site) => site.kind !== "trail_permit");
}

interface StopLike {
  sites: TrailCampground[];
}

/**
 * One stop per night in route order. At a stop with several pads, the first
 * pad that was available that night (if availability was checked for this
 * stay) or else the first listed pad. Nights past the last stop start as
 * "Not decided".
 */
export function defaultItinerary(
  stops: StopLike[],
  nights: number,
  availability?: Map<string, CampgroundAvailability> | null,
): DraftNight[] {
  const usable = stops
    .map((stop) => stop.sites.filter((site) => !site.retired && site.kind !== "trail_permit"))
    .filter((sites) => sites.length > 0);
  return Array.from({ length: nights }, (_, night) => {
    const sites = usable[night];
    if (!sites) return UNDECIDED;
    const free = availability
      ? sites.find((site) => availability.get(site.site_id)?.nights[night]?.status === "available")
      : undefined;
    return { choice: "campground", siteId: (free ?? sites[0]).site_id };
  });
}

/** Keep the nights that are still in the trip; new nights start undecided. */
export function resizeItinerary(itinerary: DraftNight[], nights: number): DraftNight[] {
  return Array.from({ length: nights }, (_, i) => itinerary[i] ?? UNDECIDED);
}

/**
 * Booked nights an edit would unmark, the same rule the API applies: the
 * night is dropped, the dates move, or its campground changes.
 */
export function bookedNightsLost(plan: TripPlan, start: string, itinerary: DraftNight[]): PlanNight[] {
  return plan.itinerary.filter((night) => {
    if (!night.booked_by_me) return false;
    const wanted = itinerary[night.night_index];
    return (
      !wanted ||
      start !== plan.start_date ||
      wanted.choice !== night.choice ||
      (wanted.siteId ?? null) !== (night.site?.id ?? null)
    );
  });
}

/** "night 3 (Mon, Oct 22) at Curator", given how to show the date. */
export function describeNight(night: PlanNight, formatDate: (iso: string) => string): string {
  const where = night.site ? ` at ${siteLabel(night.site)}` : night.choice === "outside" ? " outside Parks Canada" : "";
  return `night ${night.night_index + 1} (${formatDate(night.date)})${where}`;
}

export function siteLabel(site: { name: string; site_code: string | null; stop_name?: string | null }): string {
  if (site.stop_name && site.site_code) return `${site.stop_name} ${site.site_code}`;
  return site.name;
}

/** Joins "a", "a and b", "a, b and c". */
export function listPhrase(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** A warning when the party is larger than the campground allows, else null. */
export function groupSizeWarning(party: number, maxGroupSize: number | null | undefined): string | null {
  if (maxGroupSize == null || party <= maxGroupSize) return null;
  return `Groups here are limited to ${maxGroupSize} ${maxGroupSize === 1 ? "person" : "people"}; your party is ${party}.`;
}

// A guest's draft rides in the sign-in return URL: ?plan=<nights> with each
// night as a site id, "u" (not decided) or "o" (outside Parks Canada).

export function encodeItinerary(itinerary: DraftNight[]): string {
  return itinerary.map((n) => (n.choice === "campground" && n.siteId ? n.siteId : n.choice === "outside" ? "o" : "u")).join(".");
}

/** The draft from ?plan=, keeping only campgrounds this trail offers. */
export function decodeItinerary(code: string | null, nights: number, validSiteIds: Set<string>): DraftNight[] | null {
  if (code === null) return null;
  const parts = code ? code.split(".") : [];
  const decoded = parts.map((part): DraftNight => {
    if (part === "o") return OUTSIDE;
    if (validSiteIds.has(part)) return { choice: "campground", siteId: part };
    return UNDECIDED;
  });
  return resizeItinerary(decoded, nights);
}

/** A plan is past once its last night is before the user's own today. */
export function isPastPlan(plan: Pick<TripPlanSummary, "last_night">, today: string): boolean {
  return plan.last_night < today;
}

/** Upcoming soonest first; past most recent first. */
export function splitPlans<T extends TripPlanSummary>(plans: T[], today: string): { upcoming: T[]; past: T[] } {
  const upcoming = plans.filter((p) => !isPastPlan(p, today)).sort((a, b) => a.start_date.localeCompare(b.start_date));
  const past = plans.filter((p) => isPastPlan(p, today)).sort((a, b) => b.start_date.localeCompare(a.start_date));
  return { upcoming, past };
}

/** The trip's dates as a stay, for availability checks and alerts. */
export function planStay(plan: Pick<TripPlan, "start_date" | "nights" | "party_size">): Stay {
  return { start: plan.start_date, nights: plan.nights, party: plan.party_size };
}

export const PLAN_STATUS_LABELS: Record<PlanNightStatus, string> = {
  booked: "Booked by me",
  alert: "Alert set",
  available: "Available",
  full: "Full",
  closed: "Closed for the season",
  not_released: "Not bookable yet",
  unknown: "Couldn't tell",
  not_checked: "Not checked",
};

/** Availability answers, which go stale and so show when they were checked. */
export function isCheckedStatus(status: PlanNightStatus | null): boolean {
  return status === "available" || status === "full" || status === "closed" || status === "not_released" || status === "unknown";
}
