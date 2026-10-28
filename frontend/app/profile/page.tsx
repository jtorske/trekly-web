"use client";

import { Suspense, useEffect, useState, type ComponentProps } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Backpack, Bookmark, Footprints, Pencil, Tent } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { useProfilePhoto } from "@/app/settings/ProfilePhoto";
import { useMyGear } from "@/app/gear/useMyGear";
import { useSetups } from "@/app/gear/useSetups";
import type { Profile } from "@/lib/accountApi";
import { usePlans } from "@/lib/usePlans";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useProfile } from "@/lib/useProfile";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { publicProfilePath } from "@/lib/profilesApi";
import type { FeaturedBadges } from "@/lib/featuredBadges";
import { getFeaturedBadges } from "@/lib/featuredBadgesApi";
import { rankFor } from "@/lib/rank";
import { useUnits } from "@/lib/useUnits";
import { legacySettingsHref, sectionHref } from "@/app/settings/settingsSections";
import {
  FeaturedBadgeSlots,
  IdentityCard,
  ProfileLayout,
  ProfileSkeleton,
  ProfileTabs,
  SectionCard,
  joinedLabel,
  type TabItem,
} from "./ProfileShell";
import BadgePicker from "./BadgePicker";
import JournalTab from "./JournalTab";
import { GearSection, SavedTrailList, SetupsSection, TripsSection } from "./sections";
import shell from "./shell.module.css";

/** The owner's card: the same as a visitor's, but the photo is a button that changes it. */
function OwnerCard({
  profile,
  ...card
}: { profile: Profile } & Omit<ComponentProps<typeof IdentityCard>, "avatar" | "notice">) {
  const photo = useProfilePhoto(profile, { size: 120, alt: `${card.name}'s profile photo` });
  return <IdentityCard {...card} avatar={photo.avatar} notice={photo.status} />;
}

const TAB_KEYS = ["overview", "gear", "trails", "trips", "journal"] as const;
type TabKey = (typeof TAB_KEYS)[number];

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
  const hikes = useHikeLogs();
  const [featured, setFeatured] = useState<FeaturedBadges | null>(null);
  const [pickingBadges, setPickingBadges] = useState(false);
  const hikeCount = hikes.loading || hikes.error ? null : hikes.logs.length;

  // Deleting a hike can remove a featured badge, so reload when the count changes.
  useEffect(() => {
    const controller = new AbortController();
    getFeaturedBadges(controller.signal)
      .then(setFeatured)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFeatured({ picked: false, badges: [] });
      });
    return () => controller.abort();
  }, [hikeCount]);
  const [units] = useUnits();

  const requested = searchParams.get("tab");
  // Settings used to be a tab here; old links and emails still point at it.
  useEffect(() => {
    if (requested === "settings") router.replace(legacySettingsHref(window.location.hash));
  }, [requested, router]);

  const tab: TabKey = TAB_KEYS.includes(requested as TabKey) ? (requested as TabKey) : "overview";
  const setTab = (key: TabKey) =>
    router.replace(key === "overview" ? "/profile" : `/profile?tab=${key}`, { scroll: false });

  if (loading) return <ProfileSkeleton />;
  if (error || !profile) {
    return (
      <main className={shell.page}>
        <div className={shell.wrap}>
          <p className={ui.error} role="alert">
            Your profile didn&apos;t load. {error ?? "Try again in a moment."}{" "}
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
  const gearCount = gear.status === "ready" ? gear.items.length : gear.status === "loading" ? null : profile.counts.gear_items;
  const savedCount = savedTrails.loading
    ? null
    : savedTrails.error
      ? profile.counts.saved_trails
      : savedTrails.saved.length;
  const tripCount = plans.loading || plans.error ? null : plans.plans.length;
  const isNew = !profile.display_name && !profile.bio && !profile.avatar_path;

  const tabs: TabItem<TabKey>[] = [
    { key: "overview", label: "Overview" },
    { key: "gear", label: "My gear", count: gearCount },
    { key: "trails", label: "Saved trails", count: savedCount },
    { key: "trips", label: "Trips", count: tripCount },
    { key: "journal", label: "Journal", count: hikeCount },
  ];

  const aside = (
    <OwnerCard
      profile={profile}
      name={name}
      username={profile.username}
      links={
        profile.username && (
          <>
            <Link href={publicProfilePath(profile.username)}>View public profile</Link>
            {profile.visibility === "private" && <span className={ui.hint}>(private)</span>}
          </>
        )
      }
      bio={profile.bio}
      region={profile.home_region}
      joined={joinedLabel(profile.member_since)}
      rank={hikeCount === null ? null : rankFor(hikeCount)}
      badges={
        <FeaturedBadgeSlots badges={featured?.badges ?? []} loading={!featured} onEdit={() => setPickingBadges(true)} />
      }
      action={
        <Link href={sectionHref("edit-profile")} className={ui.secondary}>
          <Pencil size={16} aria-hidden="true" />
          Edit profile
        </Link>
      }
      stats={[
        { key: "gear", icon: Backpack, label: ["Gear item", "Gear items"], value: gearCount, onSelect: () => setTab("gear") },
        { key: "saved", icon: Bookmark, label: ["Saved trail", "Saved trails"], value: savedCount, onSelect: () => setTab("trails") },
        { key: "trips", icon: Tent, label: ["Planned trip", "Planned trips"], value: tripCount, onSelect: () => setTab("trips") },
        { key: "hiked", icon: Footprints, label: ["Trail hiked", "Trails hiked"], value: hikeCount, href: "/journal" },
      ]}
    />
  );

  return (
    <ProfileLayout aside={aside}>
      <ProfileTabs tabs={tabs} active={tab} onChange={setTab} label="Profile sections" />

      <div id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className={shell.main}>
        {tab === "overview" && (
          <>
            {isNew && (
              <div className={ui.notice}>
                <strong>Welcome to Trekly.</strong>{" "}
                <Link href={sectionHref("edit-profile")} className={ui.ghost}>
                  Add a name and photo
                </Link>
                , lay out the gear you own, and bookmark trails you want to hike.
              </div>
            )}
            <SectionCard
              id="setups"
              title="My setups"
              action={
                setups.setups.length > 0 && (
                  <Link href="/gear" className={shell.sectionLink}>
                    Manage setups →
                  </Link>
                )
              }
            >
              <SetupsSection data={setups} units={units} />
            </SectionCard>
            <div className={shell.overviewGrid}>
              <SectionCard
                id="recent-gear"
                title="Recently added gear"
                action={
                  Boolean(gearCount) && (
                    <Link href="/gear" className={shell.sectionLink}>
                      View all gear →
                    </Link>
                  )
                }
              >
                <GearSection gear={gear} units={units} limit={4} />
              </SectionCard>
              <SectionCard
                id="recent-trails"
                title="Recently saved trails"
                action={
                  Boolean(savedCount) && (
                    <button type="button" className={shell.sectionLink} onClick={() => setTab("trails")}>
                      See all →
                    </button>
                  )
                }
              >
                <SavedTrailList data={savedTrails} units={units} limit={4} />
              </SectionCard>
            </div>
          </>
        )}

        {tab === "gear" && (
          <>
            <SectionCard
              id="gear"
              title="My gear"
              count={gearCount ?? undefined}
              action={
                <Link href="/gear" className={shell.sectionLink}>
                  Manage on the Gear mat →
                </Link>
              }
            >
              <GearSection gear={gear} units={units} />
            </SectionCard>
            <SectionCard id="gear-setups" title="Setups" count={setups.loading ? undefined : setups.setups.length}>
              <SetupsSection data={setups} units={units} />
            </SectionCard>
          </>
        )}

        {tab === "trails" && (
          <SectionCard
            id="trails"
            title="Saved trails"
            count={savedCount ?? undefined}
            action={
              <Link href="/saved-trails" className={shell.sectionLink}>
                Full collection →
              </Link>
            }
          >
            <SavedTrailList data={savedTrails} units={units} />
          </SectionCard>
        )}

        {tab === "journal" && <JournalTab hikes={hikes.loading ? null : hikes.logs} owner units={units} />}

        {tab === "trips" && (
          <SectionCard id="trips" title="Trips" count={tripCount ?? undefined}>
            <TripsSection data={plans} />
          </SectionCard>
        )}
      </div>
      {pickingBadges && featured && (
        <BadgePicker
          logs={hikes.logs}
          current={featured.badges}
          onClose={() => setPickingBadges(false)}
          onSaved={(saved) => {
            setFeatured(saved);
            setPickingBadges(false);
          }}
        />
      )}
    </ProfileLayout>
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
