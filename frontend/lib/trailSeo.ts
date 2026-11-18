/**
 * What search engines and link previews see for a trail page: the title,
 * a description written from the trail's own data, its social image and
 * its schema.org structured data. Pure, so it's tested without a server.
 */
import { PROVINCE_NAMES } from "./exploreFilters.ts";
import type { TrailDetail } from "./trailsApi";
import { formatDistance, formatElevation } from "./units.ts";

const ROUTE_LABELS = { out_and_back: "out-and-back", loop: "loop", point_to_point: "point-to-point" } as const;
const DESCRIPTION_LIMIT = 160;

/** The park, else the region's first part ("Kananaskis Country, AB" -> "Kananaskis Country"). */
export function trailPlace(trail: Pick<TrailDetail, "park_name" | "region">): string {
  return trail.park_name || trail.region.split(",")[0].trim() || trail.region;
}

/** "Lake Agnes Tea House Hike – Banff National Park" (the layout adds "| Trekly"). */
export function trailTitle(trail: Pick<TrailDetail, "name" | "park_name" | "region">): string {
  return `${trail.name} Hike – ${trailPlace(trail)}`;
}

function shorten(text: string, limit: number): string {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit - 1);
  const space = cut.lastIndexOf(" ");
  return `${cut.slice(0, space > 40 ? space : cut.length).replace(/[,;:.\s]+$/, "")}…`;
}

function firstSentence(text: string | null): string | null {
  if (!text) return null;
  const match = text.trim().match(/^.+?[.!?](\s|$)/);
  return (match ? match[0] : text).trim();
}

/**
 * "An easy 7.2 km out-and-back day hike in Banff National Park, Alberta,
 * with 400 m of elevation gain. <the description's first sentence>"
 * Metric: search snippets are the same for everyone.
 */
export function trailDescription(trail: TrailDetail): string {
  const difficulty = trail.terrain === "easy" ? "An easy" : `A ${trail.terrain}`;
  const nights = trail.typical_duration_nights;
  const kind = nights && nights > 0 ? `${nights}-night backpacking trip` : "day hike";
  const distance = trail.distance_km ? `${formatDistance(Number(trail.distance_km), "metric")} ` : "";
  const route = trail.route_type ? `${ROUTE_LABELS[trail.route_type]} ` : "";
  const province = trail.province_code ? PROVINCE_NAMES[trail.province_code] : null;
  const place = [trailPlace(trail), province].filter(Boolean).join(", ");
  const gain = trail.elevation_gain_m
    ? `, with ${formatElevation(trail.elevation_gain_m, "metric")} of elevation gain`
    : "";
  const summary = `${difficulty} ${distance}${route}${kind} in ${place}${gain}.`;
  const sentence = firstSentence(trail.description);
  // The description's first sentence when it fits whole; never cut mid-sentence.
  for (const extra of [sentence, "Campsites, weather and trip planning on Trekly."]) {
    if (extra && summary.length + 1 + extra.length <= DESCRIPTION_LIMIT) return `${summary} ${extra}`;
  }
  return shorten(summary, DESCRIPTION_LIMIT);
}

/** The photo, else the route map; null for the topo fallback (the site's default card). */
export function trailImage(
  trail: Pick<TrailDetail, "photo" | "route_map" | "name">,
): { url: string; width: number; height: number; alt: string } | null {
  if (trail.photo) {
    return { url: trail.photo.hero_url, width: trail.photo.width, height: trail.photo.height, alt: trail.name };
  }
  if (trail.route_map) {
    return {
      url: trail.route_map.hero_url,
      width: trail.route_map.width,
      height: trail.route_map.height,
      alt: `Route map of ${trail.name}`,
    };
  }
  return null;
}

/** schema.org TouristAttraction for the trail page's JSON-LD. */
export function trailJsonLd(trail: TrailDetail, url: string): Record<string, unknown> {
  const image = trailImage(trail);
  const province = trail.province_code ? PROVINCE_NAMES[trail.province_code] : undefined;
  return {
    "@context": "https://schema.org",
    "@type": ["TouristAttraction", "Place"],
    name: trail.name,
    url,
    description: trail.description || trailDescription(trail),
    ...(image ? { image: image.url } : {}),
    ...(trail.latitude != null && trail.longitude != null
      ? { geo: { "@type": "GeoCoordinates", latitude: Number(trail.latitude), longitude: Number(trail.longitude) } }
      : {}),
    address: {
      "@type": "PostalAddress",
      ...(province ? { addressRegion: province } : {}),
      addressCountry: trail.country_code,
    },
    ...(trail.park_name && trail.park_type && trail.park_type !== "none"
      ? { containedInPlace: { "@type": "Park", name: trail.park_name } }
      : {}),
    touristType: "Hikers",
    isAccessibleForFree: true,
  };
}

/** JSON for a <script type="application/ld+json">: "<" escaped so no text can close the tag. */
export function jsonLdScript(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
