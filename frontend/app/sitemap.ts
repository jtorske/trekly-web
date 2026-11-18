import type { MetadataRoute } from "next";
import { absoluteUrl, trailHref } from "@/lib/site";
import { sitemapProfiles, sitemapTrails } from "@/lib/trailsServer";

// Rebuilt at most hourly, so new trails and newly opted-in profiles appear without a deploy.
export const revalidate = 3600;

// When the legal pages' text last changed (their "Last updated" dates).
const LEGAL_UPDATED = { privacy: "2026-11-10", terms: "2026-11-10" };

function date(value: string | null | undefined): Date | undefined {
  return value ? new Date(value) : undefined;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // A failed API call leaves those entries out rather than failing the whole sitemap.
  const [trails, profiles] = await Promise.all([
    sitemapTrails().catch(() => []),
    sitemapProfiles().catch(() => []),
  ]);
  const newestTrail = trails.reduce<Date | undefined>((latest, trail) => {
    const updated = date(trail.updated_at);
    return updated && (!latest || updated > latest) ? updated : latest;
  }, undefined);

  return [
    { url: absoluteUrl("/"), lastModified: newestTrail, changeFrequency: "weekly", priority: 1 },
    { url: absoluteUrl("/trail-list"), lastModified: newestTrail, changeFrequency: "weekly", priority: 0.9 },
    ...trails.map((trail) => ({
      url: absoluteUrl(trailHref({ id: "", slug: trail.slug })),
      lastModified: date(trail.updated_at),
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
    // Only profiles whose owner turned on "Let search engines show my profile".
    ...profiles.map((profile) => ({
      url: absoluteUrl(`/u/${encodeURIComponent(profile.username)}`),
      lastModified: date(profile.updated_at),
      changeFrequency: "weekly" as const,
      priority: 0.4,
    })),
    { url: absoluteUrl("/privacy"), lastModified: new Date(LEGAL_UPDATED.privacy), changeFrequency: "yearly", priority: 0.2 },
    { url: absoluteUrl("/terms"), lastModified: new Date(LEGAL_UPDATED.terms), changeFrequency: "yearly", priority: 0.2 },
  ];
}
