import type { TrailPhoto } from "./trailsApi";

export type PhotoCredit = {
  /** "Photo: Wilson Hui, CC BY 2.0", or "Photo: Jordan Torske" for the owner's own. */
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

export function photoCredit(photo: TrailPhoto): PhotoCredit {
  const name = photo.photographer.trim();
  return {
    text: photo.license ? `Photo: ${name}, ${photo.license}` : `Photo: ${name}`,
    href: safeHref(photo.source_url),
    title: photo.origin ? `View the original on ${photo.origin}` : null,
  };
}
