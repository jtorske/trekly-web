/**
 * Where Trekly lives, for canonical URLs, the sitemap and social cards, and
 * whether this deployment may be indexed at all.
 *
 * Only the production deployment is indexable: Vercel previews (and local
 * builds) answer robots.txt with "Disallow: /", send X-Robots-Tag: noindex
 * and mark every page noindex, so a preview URL never shows up in search.
 */

const FALLBACK_SITE_URL = "https://trekly-web.vercel.app";

function originOf(value: string | undefined): string | null {
  if (!value) return null;
  try {
    return new URL(value.startsWith("http") ? value : `https://${value}`).origin;
  } catch {
    return null;
  }
}

/** The public site's origin, no trailing slash. NEXT_PUBLIC_SITE_URL wins, then Vercel's production domain. */
export const SITE_URL =
  originOf(process.env.NEXT_PUBLIC_SITE_URL) ??
  originOf(process.env.VERCEL_PROJECT_PRODUCTION_URL) ??
  FALLBACK_SITE_URL;

export const SITE_NAME = "Trekly";

/** True only on Vercel's production deployment. */
export function isIndexable(env: Record<string, string | undefined> = process.env): boolean {
  return env.VERCEL_ENV === "production";
}

/** An absolute URL on the public site for a path like "/trails/lake-agnes". */
export function absoluteUrl(path: string): string {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * A trail page's path. Every API trail carries its slug; the id form is
 * only a fallback and the server answers it with a 301 to the slug.
 */
export function trailHref(trail: { slug?: string | null; id: string }, search?: string): string {
  const base = trail.slug ? `/trails/${encodeURIComponent(trail.slug)}` : `/trails?id=${encodeURIComponent(trail.id)}`;
  if (!search) return base;
  return `${base}${base.includes("?") ? "&" : "?"}${search.replace(/^[?&]/, "")}`;
}
