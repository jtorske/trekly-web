"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { useMyGear } from "@/app/gear/useMyGear";
import { useSetups } from "@/app/gear/useSetups";
import { usePlans } from "@/lib/usePlans";
import { useProfile } from "@/lib/useProfile";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { useUnits } from "@/lib/useUnits";
import EditProfileDialog from "./EditProfileDialog";
import ProfileSettings from "./ProfileSettings";
import { GearSection, SavedTrailList, SetupsSection, TripsSection } from "./sections";
import styles from "./page.module.css";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "gear", label: "My gear" },
  { key: "trails", label: "Saved trails" },
  { key: "trips", label: "Trips" },
  { key: "settings", label: "Settings" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function ProfileSkeleton() {
  return (
    <main className={styles.page} aria-busy="true">
      <div className={styles.wrap}>
        <div className={styles.header}>
          <div className={`${ui.skeleton} ${styles.skeletonAvatar}`} />
          <div className={styles.headerText}>
            <div className={`${ui.skeleton} ${styles.skeletonLine}`} />
            <div className={`${ui.skeleton} ${styles.skeletonLineShort}`} />
          </div>
        </div>
      </div>
    </main>
  );
}

function ProfileContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  // Saving in Settings broadcasts the updated profile, so this stays current.
  const { profile, error, loading, reload } = useProfile();
  const gear = useMyGear();
  const savedTrails = useSavedTrails();
  const setups = useSetups();
  const plans = usePlans();
  const [units] = useUnits();
  const [editing, setEditing] = useState(false);

  const requested = searchParams.get("tab");
  const tab: TabKey = TABS.some((t) => t.key === requested) ? (requested as TabKey) : "overview";
  const setTab = (key: TabKey) =>
    router.replace(key === "overview" ? "/profile" : `/profile?tab=${key}`, { scroll: false });

  if (loading) return <ProfileSkeleton />;
  if (error || !profile) {
    return (
      <main className={styles.page}>
        <div className={styles.wrap}>
          <p className={ui.error} role="alert">
            We couldn&apos;t load your profile{error ? `: ${error}` : "."}{" "}
            <button type="button" className={ui.ghost} onClick={reload}>
              Try again
            </button>
          </p>
        </div>
      </main>
    );
  }

  const name = profile.display_name || profile.username || user?.email?.split("@")[0] || "Trekker";
  // Live counts from the same hooks the sections use, so they always agree.
  const gearCount = gear.status === "ready" ? gear.items.length : profile.counts.gear_items;
  const savedCount = savedTrails.loading ? profile.counts.saved_trails : savedTrails.saved.length;
  const isNew = !profile.display_name && !profile.bio && !profile.avatar_path;

  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <header className={styles.header}>
          <Avatar path={profile.avatar_path} name={profile.display_name} email={profile.email} size={96} alt={`${name}'s profile photo`} />
          <div className={styles.headerText}>
            <h1 className={styles.name}>{name}</h1>
            {profile.username && <p className={styles.username}>@{profile.username}</p>}
            {profile.bio && <p className={styles.bio}>{profile.bio}</p>}
            <p className={styles.meta}>
              {[
                profile.home_region,
                profile.member_since
                  ? `Joined ${new Date(profile.member_since).toLocaleDateString(undefined, { month: "long", year: "numeric" })}`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          <button type="button" className={`${ui.secondary} ${styles.editButton}`} onClick={() => setEditing(true)}>
            Edit profile
          </button>
        </header>

        <div className={styles.stats}>
          <button type="button" className={styles.stat} onClick={() => setTab("gear")}>
            <span className={styles.statValue}>{gearCount}</span>
            <span className={styles.statLabel}>{gearCount === 1 ? "Gear item" : "Gear items"}</span>
          </button>
          <button type="button" className={styles.stat} onClick={() => setTab("trails")}>
            <span className={styles.statValue}>{savedCount}</span>
            <span className={styles.statLabel}>{savedCount === 1 ? "Saved trail" : "Saved trails"}</span>
          </button>
          <button type="button" className={styles.stat} onClick={() => setTab("trips")}>
            <span className={styles.statValue}>{plans.loading ? "–" : plans.plans.length}</span>
            <span className={styles.statLabel}>{plans.plans.length === 1 ? "Planned trip" : "Planned trips"}</span>
          </button>
        </div>

        <div className={styles.tabs} role="tablist" aria-label="Profile sections">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              id={`tab-${item.key}`}
              aria-selected={tab === item.key}
              aria-controls={`panel-${item.key}`}
              tabIndex={tab === item.key ? 0 : -1}
              className={styles.tab}
              onClick={() => setTab(item.key)}
              onKeyDown={(event) => {
                const index = TABS.findIndex((t) => t.key === tab);
                if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                  event.preventDefault();
                  const next = TABS[(index + (event.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
                  setTab(next.key);
                  document.getElementById(`tab-${next.key}`)?.focus();
                }
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        <section id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className={styles.panel}>
          {tab === "overview" && (
            <div className={styles.overview}>
              {isNew && (
                <div className={ui.notice}>
                  <strong>Welcome to Trekly.</strong>{" "}
                  <button type="button" className={ui.ghost} onClick={() => setEditing(true)}>
                    Add a name and photo
                  </button>
                  , lay out the gear you own, and bookmark trails you want to hike.
                </div>
              )}
              <div>
                <div className={styles.sectionHead}>
                  <h2 className={styles.sectionTitle}>My setups</h2>
                  {setups.setups.length > 0 && (
                    <Link href="/gear" className={ui.ghost}>
                      Open Gear →
                    </Link>
                  )}
                </div>
                <SetupsSection data={setups} units={units} />
              </div>
              <div className={styles.overviewGrid}>
                <div>
                  <div className={styles.sectionHead}>
                    <h2 className={styles.sectionTitle}>Recently added gear</h2>
                    {gearCount > 0 && (
                      <Link href="/gear" className={ui.ghost}>
                        Open Gear mat →
                      </Link>
                    )}
                  </div>
                  <GearSection gear={gear} units={units} limit={4} />
                </div>
                <div>
                  <div className={styles.sectionHead}>
                    <h2 className={styles.sectionTitle}>Recently saved trails</h2>
                    {savedCount > 0 && (
                      <button type="button" className={ui.ghost} onClick={() => setTab("trails")}>
                        See all →
                      </button>
                    )}
                  </div>
                  <SavedTrailList data={savedTrails} units={units} limit={4} />
                </div>
              </div>
            </div>
          )}

          {tab === "gear" && (
            <>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>My gear</h2>
                <Link href="/gear" className={ui.primary}>
                  Manage on the Gear mat
                </Link>
              </div>
              <GearSection gear={gear} units={units} />
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>Setups</h2>
              </div>
              <SetupsSection data={setups} units={units} />
            </>
          )}

          {tab === "trails" && (
            <>
              <div className={styles.sectionHead}>
                <h2 className={styles.sectionTitle}>Saved trails</h2>
                <Link href="/saved-trails" className={ui.ghost}>
                  Full collection →
                </Link>
              </div>
              <SavedTrailList data={savedTrails} units={units} />
            </>
          )}

          {tab === "trips" && <TripsSection data={plans} />}

          {tab === "settings" && <ProfileSettings profile={profile} />}
        </section>
      </div>
      {editing && <EditProfileDialog profile={profile} onClose={() => setEditing(false)} />}
    </main>
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<ProfileSkeleton />}>
      <RequireAuth fallback={<ProfileSkeleton />}>
        <ProfileContent />
      </RequireAuth>
    </Suspense>
  );
}
