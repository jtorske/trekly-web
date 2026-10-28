"use client";

import { createContext, Suspense, useContext, useEffect, useRef, type ReactNode } from "react";
import Link from "next/link";
import { LogOut, Mail, Ruler, ShieldCheck, Trash2, UserRound, type LucideIcon } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import type { Profile } from "@/lib/accountApi";
import { useProfile } from "@/lib/useProfile";
import {
  SETTINGS_GROUPS,
  SETTINGS_HREF,
  sectionHref,
  settingsLocation,
  type SettingsIconName,
} from "./settingsSections";
import styles from "./settings.module.css";

const ProfileContext = createContext<Profile | null>(null);

/** The signed-in profile, loaded once by the shell for every section. */
export function useSettingsProfile(): Profile {
  const profile = useContext(ProfileContext);
  if (!profile) throw new Error("useSettingsProfile is only available inside Settings.");
  return profile;
}

// The avatar menu's icon set (lucide), at its size, so the two read as one.
const ICONS: Record<SettingsIconName, LucideIcon> = {
  profile: UserRound,
  privacy: ShieldCheck,
  units: Ruler,
  email: Mail,
  signOut: LogOut,
  delete: Trash2,
};

function SettingsNav({ current }: { current: string | null }) {
  return (
    <nav className={styles.nav} aria-labelledby="settings-title">
      {SETTINGS_GROUPS.map((group, index) => (
        <div key={group.heading}>
          <h2 id={`settings-group-${index}`} className={styles.groupHeading}>
            {group.heading}
          </h2>
          <ul className={styles.items} aria-labelledby={`settings-group-${index}`}>
            {group.sections.map((section) => {
              const Icon = ICONS[section.icon];
              return (
                <li key={section.slug}>
                  <Link
                    href={sectionHref(section.slug)}
                    className={`${styles.item} ${section.danger ? styles.danger : ""}`}
                    aria-current={current === section.slug ? "page" : undefined}
                    data-section={section.slug}
                  >
                    <Icon className={styles.itemIcon} size={18} aria-hidden="true" />
                    <span className={styles.itemLabel}>{section.label}</span>
                    <span className={styles.chevron} aria-hidden="true">
                      ›
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SectionSkeleton() {
  return <div className={`${ui.skeleton} ${styles.skeletonSection}`} aria-busy="true" aria-label="Loading" />;
}

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const location = settingsLocation(pathname);
  const view = location?.explicit ? "section" : "list";
  const { profile, error, loading, reload } = useProfile();
  const contentRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLDivElement>(null);
  const previous = useRef<{ pathname: string; slug: string | null } | null>(null);
  // Opened from the list, so "← Settings" can step back instead of stacking
  // another /settings entry in the browser history.
  const cameFromList = useRef(false);

  // After moving between sections, put focus on the new section's heading
  // (or, back on the phone list, on the item just left) so keyboard and
  // screen reader users land where the page changed. Not on first load.
  useEffect(() => {
    const before = previous.current;
    previous.current = { pathname, slug: location?.slug ?? null };
    cameFromList.current = before?.pathname === SETTINGS_HREF && view === "section";
    if (!before || before.pathname === pathname) return;
    const target =
      view === "list" && window.matchMedia("(max-width: 767px)").matches
        ? navRef.current?.querySelector<HTMLElement>(`[data-section="${before.slug}"]`)
        : contentRef.current?.querySelector<HTMLElement>("[data-section-heading]");
    target?.focus({ preventScroll: true });
  }, [pathname, location?.slug, view]);

  return (
    <main className={styles.page} data-view={view}>
      <div className={styles.layout}>
        <div ref={navRef} className={styles.sidebar}>
          <h1 id="settings-title" className={styles.title}>
            Settings
          </h1>
          <SettingsNav current={location?.slug ?? null} />
        </div>
        <div ref={contentRef} className={styles.content}>
          <Link
            href={SETTINGS_HREF}
            className={styles.back}
            aria-label="Back to Settings"
            onClick={(event) => {
              if (!cameFromList.current) return;
              event.preventDefault();
              router.back();
            }}
          >
            <span aria-hidden="true">←</span> Settings
          </Link>
          {loading ? (
            <SectionSkeleton />
          ) : error || !profile ? (
            <p className={ui.error} role="alert">
              Your settings didn&apos;t load. {error ?? "Try again in a moment."}{" "}
              <button type="button" className={ui.ghost} onClick={reload}>
                Try again
              </button>
            </p>
          ) : (
            <ProfileContext.Provider value={profile}>{children}</ProfileContext.Provider>
          )}
        </div>
      </div>
    </main>
  );
}

function ShellSkeleton() {
  return (
    <main className={styles.page} aria-busy="true">
      <div className={styles.layout}>
        <div className={styles.sidebar}>
          <h1 className={styles.title}>Settings</h1>
        </div>
        <div className={styles.content}>
          <SectionSkeleton />
        </div>
      </div>
    </main>
  );
}

export default function SettingsShell({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<ShellSkeleton />}>
      <RequireAuth fallback={<ShellSkeleton />}>
        <Shell>{children}</Shell>
      </RequireAuth>
    </Suspense>
  );
}
