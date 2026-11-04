/**
 * The signed-in account menu (avatar dropdown and the mobile menu). Pure so
 * the "which item is the current page" rules can be unit tested.
 */

export interface AccountLink {
  href: string;
  label: string;
}

export const PROFILE_HREF = "/profile";
export const SUPPORT_EMAIL = "treklyusersupport@gmail.com";

/** The rows under the profile header row, before Log out. */
export const ACCOUNT_LINKS: AccountLink[] = [
  { href: "/profile?tab=trips", label: "Trips" },
  { href: "/gear", label: "Gear" },
  { href: "/alerts", label: "Alerts" },
  { href: "/settings", label: "Settings" },
];

/** Admins only (the profile's is_admin), after Settings. */
export const ADMIN_LINK: AccountLink = { href: "/admin", label: "Admin" };

/** The rows for this account: everyone's, plus Admin for admins. */
export function accountLinks(isAdmin: boolean): AccountLink[] {
  return isAdmin ? [...ACCOUNT_LINKS, ADMIN_LINK] : ACCOUNT_LINKS;
}

const under = (pathname: string, prefix: string) =>
  pathname === prefix || pathname.startsWith(`${prefix}/`);

export interface NavLink extends AccountLink {
  /** Path prefixes that mark the link as the current page. */
  match: string[];
}

/** The site sections in the header (and the mobile menu's Navigation group).
 * A trail page is opened from Explore, so it highlights Explore too. */
export const NAV_LINKS: NavLink[] = [
  { href: "/trail-list", label: "Explore", match: ["/trail-list", "/trails"] },
  { href: "/gear", label: "Gear", match: ["/gear"] },
  { href: "/journal", label: "Journal", match: ["/journal"] },
];

export const isNavCurrent = (pathname: string, link: NavLink) =>
  link.match.some((prefix) => under(pathname, prefix));

/**
 * The mobile menu's Account group: the account rows minus any that already
 * sit in its Navigation group (Gear), so nothing is listed twice.
 */
export function mobileAccountLinks(isAdmin: boolean): AccountLink[] {
  const nav = new Set(NAV_LINKS.map((link) => link.href));
  return accountLinks(isAdmin).filter((link) => !nav.has(link.href));
}

/**
 * The mobile menu's current row: an account row, or else a Navigation link
 * (the profile's gear tab counts as Gear, as in the account dropdown).
 */
export function currentMobileHref(pathname: string, search: string): string | null {
  const account = currentAccountHref(pathname, search);
  if (account) return account;
  return NAV_LINKS.find((link) => isNavCurrent(pathname, link))?.href ?? null;
}

/** A finished horizontal drag on the sheet: does it close the menu? A short
 * fast flick counts as well as a long drag; mostly-vertical drags never do. */
export function isSwipeClose(dx: number, dy: number, ms: number): boolean {
  if (dx <= 0 || Math.abs(dy) > dx) return false;
  return dx >= 72 || (dx >= 24 && dx / Math.max(ms, 1) >= 0.5);
}

/**
 * The href of the account row for the page being viewed (the profile header
 * row is PROFILE_HREF), or null. Profile tabs are told apart by `?tab=`; a
 * single trip plan counts as Trips, and the profile's gear tab as Gear.
 */
export function currentAccountHref(
  pathname: string,
  search: string,
): string | null {
  const tab = new URLSearchParams(search).get("tab");
  if (under(pathname, "/profile")) {
    if (tab === "trips") return "/profile?tab=trips";
    if (tab === "gear") return "/gear";
    // The old Settings tab, on its way to /settings.
    if (tab === "settings") return "/settings";
    // No menu row for this tab since ab3955c.
    if (tab === "trails") return null;
    return "/profile";
  }
  if (under(pathname, "/plans")) return "/profile?tab=trips";
  if (under(pathname, "/gear")) return "/gear";
  if (under(pathname, "/alerts")) return "/alerts";
  if (under(pathname, "/settings")) return "/settings";
  if (under(pathname, "/admin")) return ADMIN_LINK.href;
  return null;
}
