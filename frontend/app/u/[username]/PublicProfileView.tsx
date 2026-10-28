"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import Dialog from "@/components/Dialog";
import GearThumb from "@/components/GearThumb";
import TrailBadge from "@/components/TrailBadge";
import ui from "@/components/ui.module.css";
import GearList from "@/app/gear/GearList";
import { slotForItem } from "@/app/gear/slots";
import profileStyles from "@/app/profile/page.module.css";
import { ApiError } from "@/lib/api";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { computeMilestones, groupColour } from "@/lib/journal";
import {
  REPORT_REASONS,
  asGearItem,
  getPrivacy,
  getPublicProfile,
  reportProfile,
  type PrivacySettings,
  type PublicJournalEntry,
  type PublicProfile,
  type ReportReason,
} from "@/lib/profilesApi";
import { displayName, featuredEntries, formatHikeDate, hiddenSections } from "@/lib/publicProfile";
import { signedImageUrl } from "@/lib/storage";
import { formatStay } from "@/lib/stay";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import { formatWeight } from "@/lib/units";
import { useProfile } from "@/lib/useProfile";
import { useUnits } from "@/lib/useUnits";
import styles from "./public.module.css";

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
  const setPreview = (on: boolean) => router.replace(on ? `?preview=1` : `/u/${encodeURIComponent(handle)}`, { scroll: false });

  if (load.status === "loading") {
    return (
      <main className={profileStyles.page} aria-busy="true">
        <div className={profileStyles.wrap}>
          <div className={profileStyles.header}>
            <div className={`${ui.skeleton} ${profileStyles.skeletonAvatar}`} />
            <div className={profileStyles.headerText}>
              <div className={`${ui.skeleton} ${profileStyles.skeletonLine}`} />
              <div className={`${ui.skeleton} ${profileStyles.skeletonLineShort}`} />
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (load.status !== "ready") {
    const hiddenByModerators = isOwner && privacy?.hidden_by_moderators;
    return (
      <main className={profileStyles.page}>
        <div className={`${profileStyles.wrap} ${styles.narrow}`}>
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

  return (
    <main className={profileStyles.page}>
      <div className={profileStyles.wrap}>
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

        <header className={`${profileStyles.header} ${styles.header}`}>
          <Avatar path={profile.avatar_path} name={profile.display_name} email={null} size={96} alt={`${name}'s profile photo`} />
          <div className={profileStyles.headerText}>
            <h1 className={profileStyles.name}>{name}</h1>
            <p className={profileStyles.username}>@{profile.username}</p>
            {profile.rank && (
              <p className={styles.rank}>
                <span className={styles.rankLevel} aria-hidden="true">
                  {profile.rank.level}
                </span>
                {profile.rank.title}
              </p>
            )}
            {profile.bio && <p className={profileStyles.bio}>{profile.bio}</p>}
          </div>
          {canReport && (
            <button type="button" className={`${ui.ghost} ${styles.reportButton}`} onClick={() => setReporting(true)}>
              Report profile
            </button>
          )}
        </header>

        {profile.is_private ? (
          <div className={styles.messageCard}>
            <h2 className={styles.messageTitle}>This profile is private</h2>
            <p>{name} keeps their hikes, gear and trails to themselves.</p>
          </div>
        ) : (
          <>
            {profile.journal && <FeaturedBadges entries={profile.journal.entries} />}
            {profile.journal && <JournalSection journal={profile.journal} />}
            {profile.gear && <GearSection gear={profile.gear} units={units} />}
            {profile.saved_trails && <SavedTrailsSection trails={profile.saved_trails} />}
            {profile.trip_plans && <TripPlansSection plans={profile.trip_plans} />}
            {!profile.journal && !profile.gear && !profile.saved_trails && !profile.trip_plans && (
              <p className={styles.quiet}>{name} hasn&apos;t shared anything else yet.</p>
            )}
          </>
        )}
      </div>
      {reporting && <ReportDialog username={profile.username} name={name} onClose={() => setReporting(false)} />}
    </main>
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

function Section({ id, title, children, count }: { id: string; title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className={styles.section} aria-labelledby={`${id}-title`}>
      <div className={profileStyles.sectionHead}>
        <h2 id={`${id}-title`} className={profileStyles.sectionTitle}>
          {title}
          {count != null && <span className={styles.count}> {count}</span>}
        </h2>
      </div>
      {children}
    </section>
  );
}

function FeaturedBadges({ entries }: { entries: PublicJournalEntry[] }) {
  const featured = featuredEntries(entries);
  // computeMilestones only reads each entry's trail.
  const milestones = computeMilestones(entries as unknown as HikeLog[]).filter((m) => m.earned);
  if (featured.length === 0) return null;
  return (
    <Section id="badges" title="Featured badges">
      <ul className={styles.badges}>
        {featured.map((entry) => (
          <li key={entry.trail.id} className={styles.badgeItem}>
            <TrailBadge name={entry.trail.name} terrain={entry.trail.terrain} colour={badgeColour(entry)} hiked className={styles.badge} />
          </li>
        ))}
      </ul>
      {milestones.length > 0 && (
        <ul className={styles.milestones} aria-label="Milestones earned">
          {milestones.map((milestone) => (
            <li key={milestone.id} className={ui.chip}>
              {milestone.title}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function JournalPhoto({ path, alt }: { path: string; alt: string }) {
  const [url, setUrl] = useState<{ path: string; url: string | null } | null>(null);
  useEffect(() => {
    let live = true;
    // Visitors can sign it only while the journal is public (storage RLS).
    signedImageUrl("hike-photos", path).then((signed) => live && setUrl({ path, url: signed }));
    return () => {
      live = false;
    };
  }, [path]);
  const current = url?.path === path ? url.url : null;
  if (!current) return <span className={`${styles.photo} ${ui.skeleton}`} aria-hidden="true" />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={current} alt={alt} className={styles.photo} loading="lazy" />;
}

function JournalSection({ journal }: { journal: NonNullable<PublicProfile["journal"]> }) {
  return (
    <Section id="journal" title="Trail Journal" count={journal.entries.length}>
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
              {entry.photo_path && <JournalPhoto path={entry.photo_path} alt={`Photo from ${entry.trail.name}`} />}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function GearSection({ gear, units }: { gear: NonNullable<PublicProfile["gear"]>; units: ReturnType<typeof useUnits>[0] }) {
  return (
    <Section id="gear" title="Gear and loadouts" count={gear.items.length}>
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
                      productImage={item.product?.image}
                      photoPath={item.image_path}
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
    </Section>
  );
}

function SavedTrailsSection({ trails }: { trails: NonNullable<PublicProfile["saved_trails"]> }) {
  return (
    <Section id="saved" title="Saved trails" count={trails.length}>
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
    </Section>
  );
}

function TripPlansSection({ plans }: { plans: NonNullable<PublicProfile["trip_plans"]> }) {
  return (
    <Section id="plans" title="Trip plans" count={plans.length}>
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
    </Section>
  );
}

function ReportDialog({ username, name, onClose }: { username: string; name: string; onClose: () => void }) {
  const [reason, setReason] = useState<ReportReason | "">("");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!reason) {
      setResult({ ok: false, message: "Choose a reason." });
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      await reportProfile(username, reason, details);
      setResult({ ok: true, message: "Thanks. Our team will review this profile." });
    } catch (caught) {
      setResult({ ok: false, message: caught instanceof Error ? caught.message : "Your report didn't send. Try again." });
    } finally {
      setBusy(false);
    }
  };

  const sent = result?.ok;
  return (
    <Dialog
      title={`Report ${name}`}
      subtitle="Reports go to the Trekly team. The person you report isn't told who sent it."
      onClose={onClose}
      busy={busy}
      size="sm"
      footer={
        sent ? (
          <button type="button" className={ui.primary} onClick={onClose}>
            Done
          </button>
        ) : (
          <>
            <button type="button" className={ui.ghost} onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button type="submit" form="report-form" className={ui.danger} disabled={busy}>
              {busy ? "Sending…" : "Send report"}
            </button>
          </>
        )
      }
    >
      {sent ? (
        <p className={ui.success} role="status">
          {result.message}
        </p>
      ) : (
        <form id="report-form" className={profileStyles.form} onSubmit={submit} noValidate>
          <fieldset className={styles.reasons}>
            <legend className={ui.label}>What&apos;s wrong with this profile?</legend>
            {REPORT_REASONS.map((option) => (
              <label key={option.value} className={styles.reason}>
                <input
                  type="radio"
                  name="reason"
                  value={option.value}
                  checked={reason === option.value}
                  onChange={() => setReason(option.value)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>
          <label className={ui.field}>
            <span className={ui.label}>Details (optional)</span>
            <textarea
              className={ui.input}
              rows={3}
              maxLength={1000}
              value={details}
              onChange={(event) => setDetails(event.target.value)}
            />
          </label>
          {result && (
            <p className={ui.error} role="alert">
              {result.message}
            </p>
          )}
        </form>
      )}
    </Dialog>
  );
}
