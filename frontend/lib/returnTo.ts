/**
 * Where Settings' "← Back to profile" link goes: the page the user came from
 * when it's one of ours (their public profile, a trail, Activity…), else
 * /profile. PageMemory records the last page outside Settings as the user
 * moves around (client-side navigation never updates document.referrer); a
 * fresh load of /settings falls back to the referrer, if it's same-site.
 */

export const PROFILE_HREF = "/profile";
export const LAST_PAGE_KEY = "trekly:last-page";

// Pages that make no sense to go "back" to from Settings.
const SKIPPED = ["/settings", "/login", "/signup", "/auth", "/forgot-password", "/reset-password", "/welcome"];

function skipped(pathname: string): boolean {
  return SKIPPED.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/** A same-site path (with its query) worth going back to, or null. */
export function returnablePath(candidate: string | null | undefined, origin: string): string | null {
  if (!candidate) return null;
  let url: URL;
  try {
    url = new URL(candidate, origin);
  } catch {
    return null;
  }
  if (url.origin !== origin || skipped(url.pathname.replace(/\/+$/, "") || "/")) return null;
  return `${url.pathname}${url.search}`;
}

export interface BackLink {
  href: string;
  label: string;
}

/** The link: the remembered page, else the referrer, else /profile. */
export function backLink(remembered: string | null, referrer: string | null, origin: string): BackLink {
  const href = returnablePath(remembered, origin) ?? returnablePath(referrer, origin) ?? PROFILE_HREF;
  return { href, label: backLabel(href) };
}

/** "Back to profile" for a profile (theirs or anyone's), else plain "Back". */
export function backLabel(href: string): string {
  const path = href.split("?")[0];
  return path === PROFILE_HREF || path.startsWith("/u/") ? "Back to profile" : "Back";
}
