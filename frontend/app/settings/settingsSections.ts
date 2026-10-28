/**
 * The Settings sidebar: its groups, items and URLs. Pure so the routing
 * rules (which item is current, where /settings lands) can be unit tested.
 * Icons are named here and drawn by SettingsShell.
 */

export type SettingsIconName = "profile" | "privacy" | "units" | "email" | "signOut" | "delete";

export interface SettingsSection {
  slug: string;
  label: string;
  icon: SettingsIconName;
  /** Drawn in the warning colour (Delete account). */
  danger?: boolean;
}

export interface SettingsGroup {
  heading: string;
  sections: SettingsSection[];
}

export const SETTINGS_HREF = "/settings";

export const SETTINGS_GROUPS: SettingsGroup[] = [
  { heading: "Your profile", sections: [{ slug: "edit-profile", label: "Edit profile", icon: "profile" }] },
  { heading: "Who can see your content", sections: [{ slug: "privacy", label: "Privacy", icon: "privacy" }] },
  { heading: "Preferences", sections: [{ slug: "units", label: "Units", icon: "units" }] },
  {
    heading: "Account",
    sections: [
      { slug: "email-and-password", label: "Email and password", icon: "email" },
      { slug: "sign-out", label: "Sign out", icon: "signOut" },
      { slug: "delete-account", label: "Delete account", icon: "delete", danger: true },
    ],
  },
];

export const SETTINGS_SECTIONS: SettingsSection[] = SETTINGS_GROUPS.flatMap((group) => group.sections);

/** What /settings shows on a wide screen. */
export const DEFAULT_SECTION = "edit-profile";

export const sectionHref = (slug: string) => `${SETTINGS_HREF}/${slug}`;

export function findSection(slug: string): SettingsSection | undefined {
  return SETTINGS_SECTIONS.find((section) => section.slug === slug);
}

/**
 * Which section a settings URL is on. `explicit` is false for bare /settings:
 * wide screens show the default section beside the list, phones just the list.
 */
export function settingsLocation(pathname: string): { slug: string; explicit: boolean } | null {
  const trimmed = pathname.replace(/\/+$/, "");
  if (trimmed === SETTINGS_HREF) return { slug: DEFAULT_SECTION, explicit: false };
  if (!trimmed.startsWith(`${SETTINGS_HREF}/`)) return null;
  const slug = trimmed.slice(SETTINGS_HREF.length + 1);
  return findSection(slug) ? { slug, explicit: true } : null;
}

/**
 * Where an old `/profile?tab=settings` link should go now. The hash picked a
 * card on the old tab (#privacy, #units, #email, #password, #session, #delete).
 */
export function legacySettingsHref(hash: string): string {
  const card = hash.replace(/^#/, "");
  const slug =
    {
      privacy: "privacy",
      units: "units",
      email: "email-and-password",
      password: "email-and-password",
      session: "sign-out",
      delete: "delete-account",
    }[card] ?? null;
  return slug ? sectionHref(slug) : SETTINGS_HREF;
}
