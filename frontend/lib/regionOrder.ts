/**
 * "Which places are on your radar?": the order the park chips come in.
 *
 * Nearest first, measured from the browser's location when the site already
 * has permission (or they tap "Use my exact location"), otherwise from the
 * centre of their home province. With neither (no home, Outside Canada or
 * Prefer not to say), the list keeps its usual order.
 *
 * The location is only ever used here, in the browser, to sort; it isn't sent
 * anywhere or saved.
 */

import { REGIONS, searchRegions, type Region } from "./onboarding.ts";
import { distanceKm } from "./pastHikes.ts";
import type { ProvinceCode } from "./provinces.ts";

export interface Point {
  lat: number;
  lon: number;
}

/** Each province and territory's geographic centre, roughly. */
export const PROVINCE_CENTRES: Record<ProvinceCode, Point> = {
  BC: { lat: 53.73, lon: -127.65 },
  AB: { lat: 55.0, lon: -115.0 },
  SK: { lat: 54.0, lon: -106.0 },
  MB: { lat: 54.0, lon: -97.5 },
  ON: { lat: 50.0, lon: -86.0 },
  QC: { lat: 52.5, lon: -72.0 },
  NB: { lat: 46.5, lon: -66.2 },
  NS: { lat: 45.0, lon: -63.0 },
  PE: { lat: 46.4, lon: -63.2 },
  NL: { lat: 53.2, lon: -60.5 },
  YT: { lat: 63.6, lon: -135.8 },
  NT: { lat: 64.8, lon: -119.2 },
  NU: { lat: 66.0, lon: -95.0 },
};

export type SortOrigin =
  | { kind: "here"; point: Point }
  | { kind: "home"; province: ProvinceCode; point: Point };

/**
 * What to measure from: their location if we have it, else the centre of
 * their home province, else nothing (Outside Canada, Prefer not to say, or
 * no answer).
 */
export function sortOrigin(here: Point | null, home: string | null | undefined): SortOrigin | null {
  if (here) return { kind: "here", point: here };
  if (home && home in PROVINCE_CENTRES) {
    const province = home as ProvinceCode;
    return { kind: "home", province, point: PROVINCE_CENTRES[province] };
  }
  return null;
}

export interface RegionChip {
  region: Region;
  /** Kilometres from the origin; null when there's no origin. */
  km: number | null;
}

/** Nearest first; ties (and no origin at all) keep the list's usual order. */
export function orderRegions(regions: readonly Region[], origin: SortOrigin | null): RegionChip[] {
  const chips = regions.map((region) => ({ region, km: origin ? distanceKm(origin.point, region.centre) : null }));
  if (!origin) return chips;
  const position = (region: Region) => REGIONS.indexOf(region);
  return chips.sort((a, b) => a.km! - b.km! || position(a.region) - position(b.region));
}

/**
 * The chips to show, in order. `pinned` (picks as of the last search, so a
 * chip doesn't jump away when it's tapped) always shows at the top, whatever
 * the search; the rest are the search's matches, nearest first.
 */
export function regionChips(input: {
  query: string;
  pinned: readonly string[];
  origin: SortOrigin | null;
  provinceNames?: Record<string, string>;
}): { pinned: RegionChip[]; others: RegionChip[] } {
  const isPinned = (region: Region) => input.pinned.includes(region.slug);
  return {
    pinned: orderRegions(REGIONS.filter(isPinned), input.origin),
    others: orderRegions(
      searchRegions(input.query, input.provinceNames).filter((region) => !isPinned(region)),
      input.origin,
    ),
  };
}
