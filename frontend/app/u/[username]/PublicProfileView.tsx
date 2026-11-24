"use client";

import { useCallback, useEffect, useState } from "react";
import { setQueryParam, useQueryParam } from "@/lib/useQueryParam";
import { preloadTrailCatalogue } from "@/lib/useTrailCatalogue";
import Link from "next/link";
import { Backpack, BookOpen, Bookmark, Flag, FlaskConical, Tent } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import GearThumb from "@/components/GearThumb";
import HikePhoto from "@/components/HikePhoto";
import FollowButton from "@/components/FollowButton";
import ReportDialog from "@/components/ReportDialog";
import FollowCounts from "@/components/social/FollowCounts";
import { matImage } from "@/lib/gearImage";
import TrailBadge from "@/components/TrailBadge";
import {
  FeaturedBadgeSlots,
  IdentityCard,
  ProfileLayout,
  ProfilePanels,
  ProfileSkeleton,
  ProfileTabs,
  SectionCard,
  type TabItem,
} from "@/app/profile/ProfileShell";
import JournalTab from "@/app/profile/JournalTab";
import ActivityTab from "@/app/profile/ActivityTab";
import { usePostPages } from "@/app/activity/usePostPages";
import { getProfileActivity } from "@/lib/activityApi";
import shell from "@/app/profile/shell.module.css";
import ui from "@/components/ui.module.css";
import GearList from "@/app/gear/GearList";
import { EmptyState, TrailThumb, TripThumb } from "@/app/profile/sections";
import { slotForItem } from "@/app/gear/slots";
import profileStyles from "@/app/profile/page.module.css";
import { ApiError } from "@/lib/api";
import type { FollowState } from "@/lib/follows";
import { groupColour } from "@/lib/journal";
import {
  asGearItem,
  getPrivacy,
  getPublicProfile,
  type PrivacySettings,
  type PublicJournalEntry,
  type PublicProfile,
} from "@/lib/profilesApi";
import { displayName, formatHikeDate, hiddenSections, joinedLabel } from "@/lib/publicProfile";
import { formatStay } from "@/lib/stay";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import { formatWeight } from "@/lib/units";
import { useProfile } from "@/lib/useProfile";
import { useUnits } from "@/lib/useUnits";
import VerifiedCheck from "@/components/VerifiedCheck";
import { undatedLabel } from "@/lib/hikeDate";
import styles from "./public.module.css";
import { trailHref } from "@/lib/site";

type PublicTab = "activity" | "journal" | "gear" | "trails" | "trips";

type Load =
  | { status: "loading" }
  | { status: "ready"; profile: PublicProfile }
  | { status: "missing" }
  | { status: "error"; message: string };

const badgeColour = (entry: PublicJournalEntry) => groupColour(`region:${entry.trail.region}`);

/**
 * /u/[username]: the read-only public profile. Everyone gets the same API
 * response (the owner too), so the owner's extras here are only controls:
 * a banner saying what visitors don't see. "Preview as visitor" (from
 * Settings → Privacy or /profile, ?preview=1) shows the page without it.
 */
export default function PublicProfileView({ username }: { username: string }) {
  const { user, status } = useAuth();
  const signedIn = status === "signedIn";
  const { profile: me } = useProfile();
  const [units] = useUnits();
  const [state, setState] = useState<{ username: string; load: Load } | null>(null);
  const [privacy, setPrivacy] = useState<PrivacySettings | null>(null);
  const [reporting, setReporting] = useState(false);

  const handle = username.toLowerCase();
  const isOwner = Boolean(me?.username && me.username === handle);
  const previewParam = useQueryParam("preview");
  const preview = isOwner && previewParam === "1";

  useEffect(() => {
    if (status === "loading") return;
    const controller = new AbortController();
    getPublicProfile(handle, signedIn, controller.signal)
      .then((profile) => setState({ username: handle, load: { status: "ready", profile } }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        const load: Load =
          error instanceof ApiError && error.status === 404
            ? { status: "missing" }
            : { status: "error", message: error instanceof Error ? error.message : "This profile didn't load." };
        setState({ username: handle, load });
      });
    return () => controller.abort();
  }, [handle, status, signedIn]);

  useEffect(() => {
    if (!isOwner) return;
    const controller = new AbortController();
    getPrivacy(controller.signal).then(setPrivacy).catch(() => undefined);
    return () => controller.abort();
  }, [isOwner]);

  const load: Load = state && state.username === handle ? state.load : { status: "loading" };
  // The Activity tab, only when the API opens it to visitors (public, sharing on).
  const activityOpen = load.status === "ready" && load.profile.activity_count !== null;
  const fetchActivity = useCallback(
    (cursor: string | null, signal?: AbortSignal) => getProfileActivity(handle, cursor, signedIn, undefined, signal),
    [handle, signedIn],
  );
  const activity = usePostPages(activityOpen && status !== "loading" ? `u:${handle}:${signedIn}` : null, fetchActivity);
  // Preview and the open tab both live in the query string; changing one keeps the other.
  // Neither re-requests the page. The open tab is read only by the tab bar and the
  // panels (ProfileShell), so a click doesn't re-render this view.
  const setPreview = (on: boolean) => setQueryParam("preview", on ? "1" : null, { replace: true });
  const setTab = (key: PublicTab) => setQueryParam("tab", key);
  // Their Journal tab sums hikes against the trail catalogue; fetch it now, not on first open.
  const hasJournal = load.status === "ready" && Boolean(load.profile.journal?.entries.length);
  useEffect(() => {
    if (hasJournal) preloadTrailCatalogue().catch(() => undefined);
  }, [hasJournal]);

  if (load.status === "loading") return <ProfileSkeleton />;

  if (load.status !== "ready") {
    const hiddenByModerators = isOwner && privacy?.hidden_by_moderators;
    return (
      <main className={shell.page}>
        <div className={`${shell.wrap} ${styles.narrow}`}>
          <div className={styles.messageCard}>
            {hiddenByModerators ? (
              <>
                <h1 className={styles.messageTitle}>Your profile is hidden</h1>
                <p>
                  Trekly&apos;s moderators have hidden your public profile, so nobody else can see it. Your account and
                  everything in it still work as usual. To ask about it, email{" "}
                  <a href="mailto:treklyusersupport@gmail.com">treklyusersupport@gmail.com</a>.
                </p>
              </>
            ) : load.status === "missing" ? (
              <>
                <h1 className={styles.messageTitle}>Profile not found</h1>
                <p>There&apos;s no Trekly profile at @{handle}. Check the spelling, or it may have been removed.</p>
              </>
            ) : (
              <>
                <h1 className={styles.messageTitle}>This profile didn&apos;t load</h1>
                <p role="alert">{load.message}</p>
              </>
            )}
            <Link href="/trail-list" className={ui.secondary}>
              Explore trails
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const profile = load.profile;
  const name = displayName(profile);
  // A follow or unfollow here moves the count, and an approved follow changes what they see,
  // so the profile is fetched again (the API decides what shows).
  const onFollowChange = (follow: FollowState, followers: number) => {
    setState({ username: handle, load: { status: "ready", profile: { ...profile, follow, followers_count: followers } } });
    if (follow !== "requested") {
      void getPublicProfile(handle, signedIn)
        .then((fresh) => setState({ username: handle, load: { status: "ready", profile: fresh } }))
        .catch(() => undefined);
    }
  };
  const moveCounts = (change: { followers?: number }) =>
    setState({
      username: handle,
      load: { status: "ready", profile: { ...profile, followers_count: Math.max(profile.followers_count + (change.followers ?? 0), 0) } },
    });
  const showOwnerControls = isOwner && !preview;
  const canReport = Boolean(user) && !isOwner;
  // An owner who changes their photo elsewhere sees it here at once (useProfile hears every change).
  const avatarPath = isOwner && me ? me.avatar_path : profile.avatar_path;

  // Only the sections the owner shares come back from the API (all null when private).
  const tabs: TabItem<PublicTab>[] = [];
  if (profile.activity_count !== null) {
    tabs.push({ key: "activity", label: "Activity", count: activity.total ?? profile.activity_count });
  }
  if (profile.journal) tabs.push({ key: "journal", label: "Journal", count: profile.journal.entries.length });
  if (profile.gear) tabs.push({ key: "gear", label: "Gear", count: profile.gear.items.length });
  if (profile.saved_trails) tabs.push({ key: "trails", label: "Saved trails", count: profile.saved_trails.length });
  if (profile.trip_plans) tabs.push({ key: "trips", label: "Trips", count: profile.trip_plans.length });
  // An empty Activity tab (nothing shared yet) isn't where the page opens.
  const opening = tabs.find((t) => t.key !== "activity" || t.count !== 0) ?? tabs[0];
  const tabConfig = tabs.length > 0 ? { keys: tabs.map((t) => t.key), fallback: opening.key } : undefined;

  const banner = (preview || showOwnerControls) && (
    <>
      {preview && (
        <div className={styles.previewBar} role="status">
          <span>
            <strong>Previewing as a visitor.</strong> This is exactly what others see.
          </span>
          <button type="button" className={ui.secondary} onClick={() => setPreview(false)}>
            Exit preview
          </button>
        </div>
      )}
      {showOwnerControls && <OwnerBanner profile={profile} privacy={privacy} />}
    </>
  );

  const aside = (
    <IdentityCard
      avatar={<Avatar path={avatarPath} name={profile.display_name} email={null} size={120} alt={`${name}'s profile photo`} />}
      name={name}
      username={profile.username}
      accountLabel={profile.label}
      bio={profile.bio}
      joined={joinedLabel(profile.joined)}
      rank={profile.rank}
      province={profile.home_province}
      streak={profile.visit_streak}
      badges={profile.featured_badges && <FeaturedBadgeSlots badges={profile.featured_badges} ownerName={name} mine={isOwner} datesHidden={Boolean(profile.journal?.hide_dates)} />}
      social={
        <FollowCounts
          username={profile.username}
          name={name}
          followers={profile.followers_count}
          following={profile.following_count}
          open={profile.lists_open && !preview}
          owner={isOwner && !preview}
          signedIn={signedIn}
          requests={isOwner && !preview ? me?.counts?.follow_requests ?? 0 : 0}
          onCountsChange={moveCounts}
        />
      }
      action={
        !isOwner && (
          <div className={styles.followAction}>
            <FollowButton
              username={profile.username}
              name={name}
              state={signedIn ? profile.follow : null}
              isPrivate={profile.is_private}
              onChange={onFollowChange}
            />
            {profile.follows_you && <span className={styles.followsYou}>Follows you</span>}
          </div>
        )
      }
      footer={
        canReport && (
          <button type="button" className={`${ui.ghost} ${styles.reportButton}`} onClick={() => setReporting(true)}>
            <Flag size={14} aria-hidden="true" />
            Report profile
          </button>
        )
      }
    />
  );

  return (
    <ProfileLayout banner={banner} aside={aside} tabs={tabConfig}>
      {profile.label === "demo" && (
        <p className={styles.demoNotice}>
          <FlaskConical size={16} aria-hidden="true" />
          <span>
            <strong>{name} isn&apos;t a real person.</strong> This is a demo account, filled in to show what a
            Trekly profile looks like. <Link href="/signup">Make your own</Link>.
          </span>
        </p>
      )}
      {!profile.can_view ? (
        <div className={styles.messageCard}>
          <h2 className={styles.messageTitle}>This profile is private</h2>
          <p>
            {profile.follow === "requested"
              ? `Your request is waiting. Once ${name} approves it, you'll see what they share with followers.`
              : `${name} shares their hikes, gear and trails with approved followers only.`}
          </p>
        </div>
      ) : tabs.length === 0 ? (
        <div className={styles.messageCard}>
          <p className={styles.quiet}>{name} hasn&apos;t shared anything else yet.</p>
          <Link href="/trail-list" className={ui.secondary}>
            Explore trails
          </Link>
        </div>
      ) : (
        <>
          <ProfileTabs tabs={tabs} onChange={setTab} label={`${name}'s profile sections`} />
          <ProfilePanels
            panels={{
              activity: profile.activity_count !== null && (
                <ActivityTab
                  pages={activity}
                  owner={false}
                  signedIn={signedIn}
                  viewer={me?.username ?? null}
                  name={name}
                />
              ),
              journal: profile.journal && (
                <>
                  <JournalTab
                    hikes={profile.journal.entries}
                    owner={false}
                    units={units}
                    undatedCaption={profile.journal.hide_dates ? null : undatedLabel(null, false)}
                  />
                  {profile.journal.entries.length > 0 && <JournalSection journal={profile.journal} />}
                </>
              ),
              gear: profile.gear && <GearSection gear={profile.gear} units={units} />,
              trails: profile.saved_trails && <SavedTrailsSection trails={profile.saved_trails} />,
              trips: profile.trip_plans && <TripPlansSection plans={profile.trip_plans} />,
            }}
          />
        </>
      )}
      {reporting && <ReportDialog username={profile.username} name={name} onClose={() => setReporting(false)} />}
    </ProfileLayout>
  );
}

function OwnerBanner({ profile, privacy }: { profile: PublicProfile; privacy: PrivacySettings | null }) {
  const hidden = privacy ? hiddenSections(privacy) : [];
  return (
    <div className={`${ui.notice} ${styles.ownerBanner}`}>
      <div>
        <strong>This is your public profile.</strong>{" "}
        {profile.is_private
          ? hidden.length > 0
            ? `It's private: visitors see only your name, username and photo. Approved followers don't see: ${hidden.join(", ")}.`
            : "It's private: visitors see only your name, username and photo. Approved followers see every section below."
          : hidden.length > 0
            ? `Hidden from visitors: ${hidden.join(", ")}.`
            : "Visitors see every section below."}
        {privacy?.hide_hike_dates && !profile.is_private && " Hike dates are hidden."}
      </div>
      <div className={styles.ownerActions}>
        <Link href="/settings/privacy" className={ui.ghost}>
          Privacy settings
        </Link>
        <Link href="/profile" className={ui.ghost}>
          Edit profile
        </Link>
      </div>
    </div>
  );
}

function JournalSection({ journal }: { journal: NonNullable<PublicProfile["journal"]> }) {
  return (
    <SectionCard id="all-hikes" title="All hikes" count={journal.entries.length}>
      {journal.entries.length === 0 ? (
        <EmptyState icon={BookOpen} title="No hikes logged yet" action={{ href: "/trail-list", label: "Find your next hike" }}>
          Trails they mark as hiked will show up here.
        </EmptyState>
      ) : (
        <ul className={styles.journal}>
          {journal.entries.map((entry) => (
            <li key={entry.trail.id} className={styles.entry}>
              <TrailBadge name={entry.trail.name} terrain={entry.trail.terrain} colour={badgeColour(entry)} hiked className={styles.entryBadge} />
              <div className={styles.entryBody}>
                <span className={styles.entryTitle}>
                  <Link href={trailHref(entry.trail)} className={styles.entryTrail}>
                    {entry.trail.name}
                  </Link>
                  {entry.verified && <VerifiedCheck />}
                </span>
                <span className={profileStyles.trailMeta}>
                  {[
                    entry.trail.park_name ?? entry.trail.region,
                    entry.hiked_on ? `Hiked ${formatHikeDate(entry.hiked_on)}` : journal.hide_dates ? null : undatedLabel(null),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {entry.note && <p className={styles.note}>{entry.note}</p>}
              </div>
              {entry.photo_path && (
                <HikePhoto path={entry.photo_path} alt={`Photo from ${entry.trail.name}`} className={styles.photo} />
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

function GearSection({ gear, units }: { gear: NonNullable<PublicProfile["gear"]>; units: ReturnType<typeof useUnits>[0] }) {
  return (
    <SectionCard id="gear" title="Gear and loadouts" count={gear.items.length}>
      {gear.setups.length > 0 && (
        <ul className={profileStyles.setups}>
          {gear.setups.map((setup) => (
            <li key={setup.id}>
              <div className={`${profileStyles.setupCard} ${styles.staticCard}`}>
                <span className={profileStyles.setupThumbs} aria-hidden="true">
                  {setup.items.slice(0, 4).map((item) => (
                    <GearThumb
                      key={item.id}
                      icon={slotForItem(asGearItem(item)).icon}
                      productImage={matImage(item)}
                      alt=""
                      size="sm"
                    />
                  ))}
                </span>
                <span className={profileStyles.setupName}>{setup.name}</span>
                <span className={profileStyles.trailMeta}>
                  {setup.item_count} {setup.item_count === 1 ? "item" : "items"} · {formatWeight(setup.known_weight_g, units)}
                  {setup.items_missing_weight > 0 && " known"}
                </span>
                {setup.description && <span className={styles.setupDescription}>{setup.description}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {gear.items.length === 0 ? (
        <EmptyState icon={Backpack} title="No gear added yet" action={{ href: "/gear", label: "Start your own gear list" }}>
          Gear they own will show up here, with the weight of each piece.
        </EmptyState>
      ) : (
        <GearList items={gear.items.map(asGearItem)} units={units} />
      )}
    </SectionCard>
  );
}

function SavedTrailsSection({ trails }: { trails: NonNullable<PublicProfile["saved_trails"]> }) {
  return (
    <SectionCard id="saved" title="Saved trails" count={trails.length}>
      {trails.length === 0 ? (
        <EmptyState icon={Bookmark} title="No saved trails yet" action={{ href: "/trail-list", label: "Explore trails" }}>
          Trails they bookmark for later will show up here.
        </EmptyState>
      ) : (
        <ul className={profileStyles.trails}>
          {trails.map((trail) => (
            <li key={trail.id} className={profileStyles.trailRow}>
              <Link href={trailHref(trail)} className={profileStyles.trailLink}>
                <TrailThumb photo={trail.photo} name={trail.name} />
                <span className={profileStyles.trailText}>
                  <span className={profileStyles.trailName}>{trail.name}</span>
                  <span className={profileStyles.trailMeta}>
                    {[
                      trail.region,
                      TERRAIN_LABELS[trail.terrain],
                      trail.typical_duration_nights != null ? tripLengthLabel(trail.typical_duration_nights) : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

function TripPlansSection({ plans }: { plans: NonNullable<PublicProfile["trip_plans"]> }) {
  return (
    <SectionCard id="plans" title="Trip plans" count={plans.length}>
      {plans.length === 0 ? (
        <EmptyState icon={Tent} title="No trip plans yet" action={{ href: "/trail-list", label: "Explore trails" }}>
          Overnight trips they plan will show up here.
        </EmptyState>
      ) : (
        <ul className={profileStyles.trips}>
          {plans.map((plan) => (
            <li key={plan.id}>
              <Link href={trailHref(plan.trail)} className={profileStyles.tripCard}>
                <TripThumb photo={plan.trail.photo} name={plan.trail.name} />
                <span className={profileStyles.tripBody}>
                  <span className={profileStyles.tripTrail}>{plan.title ?? plan.trail.name}</span>
                  {plan.title && <span className={profileStyles.tripMeta}>{plan.trail.name}</span>}
                  <span className={profileStyles.tripMeta}>{formatStay(plan.start_date, plan.nights)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
