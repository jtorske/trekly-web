"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Backpack, Bookmark, Flag, Footprints, Tent } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import GearThumb from "@/components/GearThumb";
import HikePhoto from "@/components/HikePhoto";
import ReportDialog from "@/components/ReportDialog";
import { matImage } from "@/lib/gearImage";
import TrailBadge from "@/components/TrailBadge";
import {
  FeaturedBadgeSlots,
  IdentityCard,
  ProfileLayout,
  ProfilePanel,
  ProfileSkeleton,
  ProfileTabs,
  SectionCard,
  type StatRow,
  type TabItem,
} from "@/app/profile/ProfileShell";
import JournalTab from "@/app/profile/JournalTab";
import shell from "@/app/profile/shell.module.css";
import ui from "@/components/ui.module.css";
import GearList from "@/app/gear/GearList";
import { slotForItem } from "@/app/gear/slots";
import profileStyles from "@/app/profile/page.module.css";
import { ApiError } from "@/lib/api";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { computeMilestones, groupColour } from "@/lib/journal";
import {
  asGearItem,
  getPrivacy,
  getPublicProfile,
  type PrivacySettings,
  type PublicJournalEntry,
  type PublicProfile,
} from "@/lib/profilesApi";
import { displayName, formatHikeDate, hiddenSections } from "@/lib/publicProfile";
import { formatStay } from "@/lib/stay";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import { formatWeight } from "@/lib/units";
import { useProfile } from "@/lib/useProfile";
import { useUnits } from "@/lib/useUnits";
import styles from "./public.module.css";

type PublicTab = "journal" | "gear" | "trails" | "trips";

type Load =
  | { status: "loading" }
  | { status: "ready"; profile: PublicProfile }
  | { status: "missing" }
  | { status: "error"; message: string };

const badgeColour = (entry: PublicJournalEntry) => groupColour(`region:${entry.trail.region}`);

/**
 * /u/[username]: the read-only public profile. Everyone gets the same API
 * response (the owner too), so the owner's extras here are only controls:
 * a banner saying what visitors don't see, and "Preview as visitor", which
 * shows the page with those controls removed.
 */
export default function PublicProfileView({ username }: { username: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const { profile: me } = useProfile();
  const [units] = useUnits();
  const [state, setState] = useState<{ username: string; load: Load } | null>(null);
  const [privacy, setPrivacy] = useState<PrivacySettings | null>(null);
  const [reporting, setReporting] = useState(false);

  const handle = username.toLowerCase();
  const isOwner = Boolean(me?.username && me.username === handle);
  const preview = isOwner && searchParams.get("preview") === "1";

  useEffect(() => {
    const controller = new AbortController();
    getPublicProfile(handle, controller.signal)
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
  }, [handle]);

  useEffect(() => {
    if (!isOwner) return;
    const controller = new AbortController();
    getPrivacy(controller.signal).then(setPrivacy).catch(() => undefined);
    return () => controller.abort();
  }, [isOwner]);

  const load: Load = state && state.username === handle ? state.load : { status: "loading" };
  // Preview and the open tab both live in the query string; changing one keeps the other.
  const go = (changes: Record<string, string | null>) => {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) params.delete(key);
      else params.set(key, value);
    }
    const query = params.toString();
    router.replace(`/u/${encodeURIComponent(handle)}${query ? `?${query}` : ""}`, { scroll: false });
  };
  const setPreview = (on: boolean) => go({ preview: on ? "1" : null });
  const setTab = (key: PublicTab) => go({ tab: key });

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
  const showOwnerControls = isOwner && !preview;
  const canReport = Boolean(user) && !isOwner;
  // An owner who changes their photo elsewhere sees it here at once (useProfile hears every change).
  const avatarPath = isOwner && me ? me.avatar_path : profile.avatar_path;

  // Only the sections the owner shares come back from the API (all null when private).
  const tabs: TabItem<PublicTab>[] = [];
  if (profile.journal) tabs.push({ key: "journal", label: "Journal", count: profile.journal.entries.length });
  if (profile.gear) tabs.push({ key: "gear", label: "Gear", count: profile.gear.items.length });
  if (profile.saved_trails) tabs.push({ key: "trails", label: "Saved trails", count: profile.saved_trails.length });
  if (profile.trip_plans) tabs.push({ key: "trips", label: "Trips", count: profile.trip_plans.length });
  const requested = searchParams.get("tab");
  const tab = tabs.find((t) => t.key === requested)?.key ?? tabs[0]?.key ?? null;

  const stats: StatRow[] = [];
  if (profile.gear) {
    stats.push({ key: "gear", icon: Backpack, label: ["Gear item", "Gear items"], value: profile.gear.items.length, onSelect: () => setTab("gear") });
  }
  if (profile.saved_trails) {
    stats.push({ key: "saved", icon: Bookmark, label: ["Saved trail", "Saved trails"], value: profile.saved_trails.length, onSelect: () => setTab("trails") });
  }
  if (profile.trip_plans) {
    stats.push({ key: "trips", icon: Tent, label: ["Planned trip", "Planned trips"], value: profile.trip_plans.length, onSelect: () => setTab("trips") });
  }
  if (profile.journal) {
    stats.push({ key: "hiked", icon: Footprints, label: ["Trail hiked", "Trails hiked"], value: profile.journal.entries.length, onSelect: () => setTab("journal") });
  }

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
      {showOwnerControls && <OwnerBanner profile={profile} privacy={privacy} onPreview={() => setPreview(true)} />}
    </>
  );

  const aside = (
    <IdentityCard
      avatar={<Avatar path={avatarPath} name={profile.display_name} email={null} size={120} alt={`${name}'s profile photo`} />}
      name={name}
      username={profile.username}
      bio={profile.bio}
      rank={profile.rank}
      badges={profile.featured_badges && <FeaturedBadgeSlots badges={profile.featured_badges} />}
      stats={stats}
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
    <ProfileLayout banner={banner} aside={aside}>
      {profile.is_private ? (
        <div className={styles.messageCard}>
          <h2 className={styles.messageTitle}>This profile is private</h2>
          <p>{name} keeps their hikes, gear and trails to themselves.</p>
        </div>
      ) : tab === null ? (
        <div className={styles.messageCard}>
          <p className={styles.quiet}>{name} hasn&apos;t shared anything else yet.</p>
        </div>
      ) : (
        <>
          <ProfileTabs tabs={tabs} active={tab} onChange={setTab} label={`${name}'s profile sections`} />
          <ProfilePanel tab={tab}>
            {tab === "journal" && profile.journal && (
              <>
                <JournalTab hikes={profile.journal.entries} owner={false} units={units} />
                {profile.journal.entries.length > 0 && <JournalSection journal={profile.journal} />}
              </>
            )}
            {tab === "gear" && profile.gear && <GearSection gear={profile.gear} units={units} />}
            {tab === "trails" && profile.saved_trails && <SavedTrailsSection trails={profile.saved_trails} />}
            {tab === "trips" && profile.trip_plans && <TripPlansSection plans={profile.trip_plans} />}
          </ProfilePanel>
        </>
      )}
      {reporting && <ReportDialog username={profile.username} name={name} onClose={() => setReporting(false)} />}
    </ProfileLayout>
  );
}

function OwnerBanner({
  profile,
  privacy,
  onPreview,
}: {
  profile: PublicProfile;
  privacy: PrivacySettings | null;
  onPreview: () => void;
}) {
  const hidden = privacy ? hiddenSections(privacy) : [];
  return (
    <div className={`${ui.notice} ${styles.ownerBanner}`}>
      <div>
        <strong>This is your public profile.</strong>{" "}
        {profile.is_private
          ? "It's private: visitors see only your name, username and photo."
          : hidden.length > 0
            ? `Hidden from visitors: ${hidden.join(", ")}.`
            : "Visitors see every section below."}
        {privacy?.hide_hike_dates && !profile.is_private && " Hike dates are hidden."}
      </div>
      <div className={styles.ownerActions}>
        <button type="button" className={ui.secondary} onClick={onPreview}>
          Preview as visitor
        </button>
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

function Milestones({ entries }: { entries: PublicJournalEntry[] }) {
  // computeMilestones only reads each entry's trail.
  const milestones = computeMilestones(entries as unknown as HikeLog[]).filter((m) => m.earned);
  if (milestones.length === 0) return null;
  return (
    <ul className={styles.milestones} aria-label="Milestones earned">
      {milestones.map((milestone) => (
        <li key={milestone.id} className={ui.chip}>
          {milestone.title}
        </li>
      ))}
    </ul>
  );
}

function JournalSection({ journal }: { journal: NonNullable<PublicProfile["journal"]> }) {
  return (
    <SectionCard id="all-hikes" title="All hikes" count={journal.entries.length}>
      <Milestones entries={journal.entries} />
      {journal.entries.length === 0 ? (
        <p className={styles.quiet}>No hikes logged yet.</p>
      ) : (
        <ul className={styles.journal}>
          {journal.entries.map((entry) => (
            <li key={entry.trail.id} className={styles.entry}>
              <TrailBadge name={entry.trail.name} terrain={entry.trail.terrain} colour={badgeColour(entry)} hiked className={styles.entryBadge} />
              <div className={styles.entryBody}>
                <Link href={`/trails?id=${encodeURIComponent(entry.trail.id)}`} className={styles.entryTrail}>
                  {entry.trail.name}
                </Link>
                <span className={profileStyles.trailMeta}>
                  {[entry.trail.region, entry.hiked_on ? `Hiked ${formatHikeDate(entry.hiked_on)}` : null].filter(Boolean).join(" · ")}
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
        <p className={styles.quiet}>No gear added yet.</p>
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
        <p className={styles.quiet}>No saved trails yet.</p>
      ) : (
        <ul className={profileStyles.trails}>
          {trails.map((trail) => (
            <li key={trail.id} className={profileStyles.trailRow}>
              <Link href={`/trails?id=${encodeURIComponent(trail.id)}`} className={profileStyles.trailLink}>
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
        <p className={styles.quiet}>No trip plans yet.</p>
      ) : (
        <ul className={profileStyles.trips}>
          {plans.map((plan) => (
            <li key={plan.id}>
              <Link href={`/trails?id=${encodeURIComponent(plan.trail.id)}`} className={profileStyles.tripCard}>
                <span className={profileStyles.tripTrail}>{plan.title ?? plan.trail.name}</span>
                {plan.title && <span className={profileStyles.tripMeta}>{plan.trail.name}</span>}
                <span className={profileStyles.tripMeta}>{formatStay(plan.start_date, plan.nights)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
