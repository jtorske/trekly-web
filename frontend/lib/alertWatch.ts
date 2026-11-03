import type { ParkType, TrailAlerts, TrailPickItem } from "./trailsApi";

/**
 * Which trails the "Add an alert" dialog can offer, and what to say about
 * the ones it can't. Whether a trail is watchable comes from the server
 * (has_watchable_campgrounds); this only words it and decides what a pick does.
 */

export const ALERTS_WORK_FOR = "Alerts work for Parks Canada campgrounds.";

const PARK_KIND: Partial<Record<ParkType, string>> = {
  national: "National park",
  provincial: "Provincial park",
  regional: "Regional park",
};

type ReasonFacts = Pick<TrailAlerts, "trail_permit" | "booked_through"> & { park_type: ParkType | null };

/** One or two short sentences on why alerts can't watch this trail. */
export function unwatchableReason(trail: ReasonFacts): string {
  if (trail.trail_permit) {
    return "Parks Canada books this trail as a permit, not by campground. Alerts can't watch permits.";
  }
  const booking = trail.booked_through;
  if (booking?.system === "none") return `No reservations: first come, first served. ${ALERTS_WORK_FOR}`;
  if (booking && booking.system !== "parks_canada") {
    const kind = trail.park_type ? PARK_KIND[trail.park_type] : undefined;
    return `${kind ? `${kind}: book` : "Book"} through ${booking.name}. ${ALERTS_WORK_FOR}`;
  }
  return `No online Parks Canada booking. ${ALERTS_WORK_FOR}`;
}

/**
 * The dialog's search. Without a query the list shows only watchable trails,
 * unless "Show trails without alerts" is on; a typed search always finds the
 * others too (greyed out, below), so people learn why theirs isn't offered.
 */
export function pickerSearch(query: string, showUnwatchable: boolean): { watchable?: true; sort: "watchable" } {
  return query.trim() === "" && !showUnwatchable ? { watchable: true, sort: "watchable" } : { sort: "watchable" };
}

/** Watchable trails first, each group in the order the server sent it. */
export function pickerOrder<T extends Pick<TrailPickItem, "has_watchable_campgrounds">>(trails: T[]): T[] {
  return [...trails.filter((t) => t.has_watchable_campgrounds), ...trails.filter((t) => !t.has_watchable_campgrounds)];
}

/**
 * What choosing a row does, by click, Enter or Space alike: a watchable
 * trail moves on to its campgrounds; any other only explains itself and
 * stays unselected.
 */
export function choosePickerTrail<T extends Pick<TrailPickItem, "has_watchable_campgrounds"> & ReasonFacts>(
  trail: T,
): { kind: "pick"; trail: T } | { kind: "explain"; reason: string } {
  return trail.has_watchable_campgrounds ? { kind: "pick", trail } : { kind: "explain", reason: unwatchableReason(trail) };
}
