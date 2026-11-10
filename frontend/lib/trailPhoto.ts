import type { TrailPhoto } from "./trailsApi";

export type PhotoCredit = {
  /**
   * "Photo: Wilson Hui, CC BY 2.0", "Photo: Jordan Torske" for the owner's own,
   * or "Photo: Jasper National Park · Wilson Hui, CC BY 2.0" for a photo of the
   * park rather than this trail.
   */
  text: string;
  /** The photo's source page, when it has one we can safely link to. */
  href: string | null;
  /** Tooltip with where the photo was first published. */
  title: string | null;
};

function safeHref(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/**
 * `place` is the trail's park (or region, for trails in no park); a
 * park-level photo names it, so it's clear the photo isn't of the trail itself.
 */
export function photoCredit(photo: TrailPhoto, place?: string | null): PhotoCredit {
  const name = photo.photographer.trim();
  const who = photo.license ? `${name}, ${photo.license}` : name;
  const where = photo.scope === "park" && place?.trim() ? `${place.trim()} · ` : "";
  return {
    text: `Photo: ${where}${who}`,
    href: safeHref(photo.source_url),
    title: photo.origin ? `View the original on ${photo.origin}` : null,
  };
}

/** The credit under a route-map hero: the line is OpenStreetMap's, the terrain NRCan's. */
export const ROUTE_MAP_CREDIT = {
  text: "Map: route © OpenStreetMap contributors · terrain NRCan",
  href: "https://www.openstreetmap.org/copyright",
  title: "Route data © OpenStreetMap contributors (ODbL); elevation MRDEM-30, Natural Resources Canada (Open Government Licence – Canada)",
} as const;

/** Where the photo credit's park comes from: the park, else the region ("Kananaskis, AB"). */
export function creditPlace(trail: { park_name?: string | null; region?: string | null }): string | null {
  return trail.park_name?.trim() || trail.region?.trim() || null;
}
