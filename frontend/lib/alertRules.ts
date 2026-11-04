import type { TrailCampground } from "./trailsApi";

/**
 * How many people an alert can ask for. The API enforces the same limit
 * (backend app/backcountry/alertable.py); which campgrounds an alert can
 * watch at all comes with each campground as `watchable`.
 */

/** Parks Canada's maximum group size for the site, when the party is over it. */
export function partyLimitProblem(site: Pick<TrailCampground, "name" | "max_group_size">, party: number): string | null {
  const limit = site.max_group_size;
  if (!limit || party <= limit) return null;
  return `${site.name} takes at most ${limit} ${limit === 1 ? "person" : "people"} per booking.`;
}
