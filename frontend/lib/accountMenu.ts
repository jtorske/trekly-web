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
  { href: "/profile?tab=trips", label: "My trips" },
  { href: "/gear", label: "My gear" },
  { href: "/alerts", label: "Alerts" },
  { href: "/profile?tab=settings", label: "Settings" },
  { href: `mailto:${SUPPORT_EMAIL}`, label: "Contact support" },
];

const under = (pathname: string, prefix: string) => pathname === prefix || pathname.startsWith(`${prefix}/`);

/**
 * The href of the account row for the page being viewed (the profile header
 * row is PROFILE_HREF), or null. Profile tabs are told apart by `?tab=`; a
 * single trip plan counts as My trips, and the profile's gear tab as My gear.
 */
export function currentAccountHref(pathname: string, search: string): string | null {
  const tab = new URLSearchParams(search).get("tab");
  if (under(pathname, "/profile")) {
    if (tab === "trips") return "/profile?tab=trips";
    if (tab === "settings") return "/profile?tab=settings";
    if (tab === "gear") return "/gear";
    if (tab === "trails") return null;
    return "/profile";
  }
  if (under(pathname, "/plans")) return "/profile?tab=trips";
  if (under(pathname, "/gear")) return "/gear";
  if (under(pathname, "/alerts")) return "/alerts";
  return null;
}
