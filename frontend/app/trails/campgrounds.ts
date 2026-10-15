/**
 * Presentation rules for a trail's "Campgrounds on this route" section:
 * grouping pads into stops, kind labels, capacity copy and booking notes.
 * Pure so they can be unit tested.
 */

import type { CampgroundKind, TrailBooking, TrailCampground, TrailCampgrounds } from "@/lib/trailsApi";

const PARKS_CANADA = "parks_canada";

export interface Stop {
  key: string;
  /** "Fish Harbour" for a group of pads, otherwise the campground's name. */
  label: string;
  sites: TrailCampground[];
  /** Every site at the stop has been retired by the provider. */
  retired: boolean;
}

/**
 * Consecutive links that share a route position and stop name are one stop
 * (individually booked pads at the same place). Links arrive in route order.
 */
export function groupStops(campgrounds: TrailCampground[]): Stop[] {
  const stops: Stop[] = [];
  for (const site of campgrounds) {
    const last = stops[stops.length - 1];
    if (
      last &&
      site.stop_name &&
      last.sites[0].stop_name === site.stop_name &&
      last.sites[0].route_order === site.route_order
    ) {
      last.sites.push(site);
      last.retired = last.retired && site.retired;
      continue;
    }
    stops.push({
      key: site.site_id,
      label: site.stop_name ?? site.name,
      sites: [site],
      retired: site.retired,
    });
  }
  return stops;
}

const KIND_LABELS: Record<CampgroundKind, string> = {
  zone: "Campground",
  site: "Campsite",
  shelter: "Shelter",
  cabin: "Cabin",
  yurt: "Yurt",
  random_zone: "Random camping",
  horse_camp: "Horse camp",
  backpacking_campground: "Campground",
  trail_permit: "Trail permit",
  other: "Backcountry",
};

export function kindLabel(kind: CampgroundKind, count = 1): string {
  if (kind === "site" && count > 1) return `${count} campsites`;
  return KIND_LABELS[kind] ?? "Backcountry";
}

/** Short capacity facts, e.g. ["Quota 8 a night", "Groups up to 6"]. */
export function capacityFacts(site: TrailCampground): string[] {
  const facts: string[] = [];
  if (site.reservable_capacity != null && site.kind !== "random_zone") {
    facts.push(
      site.kind === "trail_permit"
        ? `Quota ${site.reservable_capacity} a day`
        : `Quota ${site.reservable_capacity} a night`,
    );
  }
  const group = site.max_group_size ?? site.max_capacity;
  if (group != null) facts.push(`Groups up to ${group}`);
  return facts;
}

/** "Booked through BC Parks", or "Booked outside Trekly" when we haven't confirmed the system. */
export function bookingLabel(booking: TrailBooking): string {
  if (!booking.confirmed || !booking.name) return "Booked outside Trekly";
  if (booking.system === "none") return booking.name;
  return `Booked through ${booking.name}`;
}

export interface CampgroundView {
  /** Show the section at all. */
  visible: boolean;
  stops: Stop[];
  /** The Parks Canada entry when it books the listed campgrounds. */
  parksCanada: TrailBooking | null;
  /** Notes for every system whose sites we don't list. */
  elsewhere: TrailBooking[];
}

export function campgroundView(data: TrailCampgrounds | null): CampgroundView {
  if (!data) return { visible: false, stops: [], parksCanada: null, elsewhere: [] };
  const stops = groupStops(data.campgrounds);
  const parksCanada =
    stops.length > 0 ? data.booking.find((b) => b.system === PARKS_CANADA) ?? null : null;
  const elsewhere = data.booking.filter((b) => b !== parksCanada);
  const showsTrip = data.trip_type === "overnight" || data.overnight_option;
  return {
    visible: showsTrip && (stops.length > 0 || elsewhere.length > 0),
    stops,
    parksCanada,
    elsewhere,
  };
}
