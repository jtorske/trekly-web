"use client";

import { Suspense, useCallback, useEffect, useState, type ComponentProps } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Pencil } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { setQueryParam } from "@/lib/useQueryParam";
import { preloadTrailCatalogue } from "@/lib/useTrailCatalogue";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { useProfilePhoto } from "@/app/settings/ProfilePhoto";
import { useMyGear } from "@/app/gear/useMyGear";
import { useSetups } from "@/app/gear/useSetups";
import type { Profile } from "@/lib/accountApi";
import { getMyActivity } from "@/lib/activityApi";
import { getPrivacy, type PrivacySettings } from "@/lib/profilesApi";
import { usePostPages } from "@/app/activity/usePostPages";
import { usePlans } from "@/lib/usePlans";
import { undatedLabel } from "@/lib/hikeDate";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useProfile } from "@/lib/useProfile";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { publicProfilePath } from "@/lib/profilesApi";
import type { FeaturedBadges } from "@/lib/featuredBadges";
import { getFeaturedBadges } from "@/lib/featuredBadgesApi";
import { useRank } from "@/lib/useRank";
import { useStreak } from "@/lib/useStreak";
import { useUnits } from "@/lib/useUnits";
import { legacySettingsHref, sectionHref } from "@/app/settings/settingsSections";
import {
  FeaturedBadgeSlots,
  IdentityCard,
  ProfileLayout,
  ProfilePanels,
  ProfileSkeleton,
  ProfileTabs,
  SectionCard,
  type TabItem,
} from "./ProfileShell";
import FollowCounts from "@/components/social/FollowCounts";
import { joinedLabel } from "@/lib/publicProfile";
import BadgePicker from "./BadgePicker";
import { RankProgress } from "./RankDetails";
import JournalTab from "./JournalTab";
import ActivityTab from "./ActivityTab";
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

// Activity first, like a profile feed; old ?tab=overview links land on it.
const TAB_KEYS = ["activity", "journal", "gear", "trails", "trips"] as const;
type TabKey = (typeof TAB_KEYS)[number];
const TAB_CONFIG = { keys: [...TAB_KEYS], fallback: "activity" };

function ProfileContent() {
  const router = useRouter();
  const { user } = useAuth();
  // Saving in Settings broadcasts the updated profile, so this stays current.
  const { profile, error, loading, reload } = useProfile();
  const gear = useMyGear();
  const savedTrails = useSavedTrails();
  const setups = useSetups();
  const plans = usePlans();
  const hikes = useHikeLogs();
  const { rank: myRank } = useRank();
  const { streak, grew: streakGrew } = useStreak();
  const [featured, setFeatured] = useState<FeaturedBadges | null>(null);
  const [pickingBadges, setPickingBadges] = useState(false);
  // Their own posts, for the Activity tab.
  const fetchActivity = useCallback(
    (cursor: string | null, signal?: AbortSignal) => getMyActivity(cursor, undefined, signal),
    [],
  );
  const activity = usePostPages(user ? `me:${user.id}` : null, fetchActivity);
  const [privacy, setPrivacy] = useState<PrivacySettings | null>(null);
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    getPrivacy(controller.signal).then(setPrivacy).catch(() => undefined);
    return () => controller.abort();
  }, [user]);
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

  // The Journal tab sums hikes against the trail catalogue; fetch it now, not on first open.
  useEffect(() => {
    preloadTrailCatalogue().catch(() => undefined);
  }, []);

  // Settings used to be a tab here; old links and emails still point at it.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("tab") === "settings") {
      router.replace(legacySettingsHref(window.location.hash));
    }
  }, [router]);

  // The open tab lives in the URL and is read only by the tab bar and the panels
  // (ProfileShell), so a click doesn't re-render this page.
  const setTab = (key: TabKey) => setQueryParam("tab", key === "activity" ? null : key);

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
    { key: "activity", label: "Activity", count: activity.error ? undefined : activity.total },
    { key: "journal", label: "Journal", count: hikeCount },
    { key: "gear", label: "My gear", count: gearCount },
    { key: "trails", label: "Saved trails", count: savedCount },
    { key: "trips", label: "Trips", count: tripCount },
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
            <Link href={`${publicProfilePath(profile.username)}?preview=1`}>Preview as visitor</Link>
            {profile.visibility === "private" && <span className={ui.hint}>(private)</span>}
          </>
        )
      }
      social={
        profile.username && (
          <FollowCounts
            username={profile.username}
            name={name}
            followers={profile.counts.followers}
            following={profile.counts.following}
            open
            owner
            signedIn
            requests={profile.counts.follow_requests}
            onCountsChange={() => void reload()}
          />
        )
      }
      bio={profile.bio}
      region={profile.home_region}
      joined={joinedLabel(profile.member_since)}
      rank={myRank?.rank ?? null}
      rankDetail={myRank && <RankProgress mine={myRank} />}
      province={profile.home_province}
      streak={streak}
      streakGrew={streakGrew}
      badges={
        <FeaturedBadgeSlots badges={featured?.badges ?? []} ownerName={name} mine loading={!featured} onEdit={() => setPickingBadges(true)} />
      }
      action={
        <Link href={sectionHref("edit-profile")} className={ui.secondary}>
          <Pencil size={16} aria-hidden="true" />
          Edit profile
        </Link>
      }
    />
  );

  return (
    <ProfileLayout aside={aside} tabs={TAB_CONFIG}>
      <ProfileTabs tabs={tabs} onChange={setTab} label="Profile sections" />

      <ProfilePanels
        panels={{
          activity: (
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
            <ActivityTab
              pages={activity}
              owner
              signedIn
              viewer={profile.username}
              name={name}
              privacy={privacy}
              onPrivacy={setPrivacy}
            />
          </>
          ),

          gear: (
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
            <SectionCard
              id="gear-setups"
              title="My setups"
              count={setups.loading ? undefined : setups.setups.length}
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
          </>
          ),

          trails: (
          <SectionCard id="trails" title="Saved trails" count={savedCount ?? undefined}>
            <SavedTrailList data={savedTrails} units={units} />
          </SectionCard>
          ),

          journal: <JournalTab
            hikes={hikes.loading ? null : hikes.logs}
            owner
            units={units}
            undatedCaption={undatedLabel(user?.created_at, false)}
          />,

          trips: (
          <SectionCard id="trips" title="Trips" count={tripCount ?? undefined}>
            <TripsSection data={plans} />
          </SectionCard>
          ),
        }}
      />
      {pickingBadges && featured && (
        <BadgePicker
          logs={hikes.logs}
          homeProvince={profile.home_province}
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
