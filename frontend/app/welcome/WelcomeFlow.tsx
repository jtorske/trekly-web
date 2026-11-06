"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Backpack,
  Compass,
  Footprints,
  Globe,
  Lock,
  Mountain,
  Ruler,
  Sprout,
  Sun,
  Tent,
} from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import ProvinceBadge from "@/components/ProvinceBadge";
import SaveTrailButton from "@/components/SaveTrailButton";
import TrailPhoto from "@/components/TrailPhoto";
import UsernameField, { useUsernameStatus } from "@/components/UsernameField";
import { ChoiceCards, ExperienceCards, HikingStyleCards, InterestChips, RegionPicker } from "@/components/OnboardingChoices";
import ui from "@/components/ui.module.css";
import { getProfile, updateProfile, type Profile, type ProfileUpdate } from "@/lib/accountApi";
import { addMyGear, type ProductSummary } from "@/lib/gearApi";
import { addPastHikes } from "@/lib/hikeLogsApi";
import { DEFAULT_AFTER_LOGIN, safeNextPath } from "@/lib/authLogic";
import {
  EXPLORE_HREF,
  QUESTION_COUNT,
  isOptional,
  nextStep,
  previousStep,
  resumeStep,
  stepNumber,
  type Experience,
  type HikingStyle,
  type StepKey,
} from "@/lib/onboarding";
import {
  getPreferences,
  getRecommendations,
  updatePreferences,
  type Preferences,
  type PreferencesUpdate,
} from "@/lib/preferencesApi";
import { getPrivacy, updatePrivacy, type PrivacySettings } from "@/lib/profilesApi";
import { PROVINCES, homeLabel, province as provinceByCode, type ProvinceCode } from "@/lib/provinces";
import { TERRAIN_LABELS } from "@/lib/terrain";
import type { TrailListItem } from "@/lib/trailsApi";
import { formatDistance, formatElevation, formatTrailDistance, type UnitSystem } from "@/lib/units";
import { announceProfile, useProfile } from "@/lib/useProfile";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { normalizeUsername, suggestionHint, usernameReady } from "@/lib/usernames";
import { useProfilePhoto } from "../settings/ProfilePhoto";
import { HikedStep, PackStep } from "./HistorySteps";
import styles from "./welcome.module.css";

// ---------------------------------------------------------------- visuals

type Visual = { kind: "photo"; src: string; position?: string } | { kind: "topo"; tone: "olive" | "dusk" | "rust" | "sand" };

/** A different landing photo or topo panel behind every screen. */
const VISUALS: Record<StepKey, Visual> = {
  name: { kind: "photo", src: "/images/IMG_8873.jpeg", position: "center 35%" },
  photo: { kind: "topo", tone: "olive" },
  home: { kind: "photo", src: "/images/IMG_9031.jpeg", position: "center 60%" },
  style: { kind: "photo", src: "/images/IMG_9627.jpg", position: "center 55%" },
  experience: { kind: "topo", tone: "dusk" },
  interests: { kind: "photo", src: "/images/IMG_9332.jpeg", position: "center 60%" },
  regions: { kind: "photo", src: "/images/IMG_9336.jpeg", position: "center 55%" },
  hiked: { kind: "topo", tone: "olive" },
  pack: { kind: "topo", tone: "sand" },
  units: { kind: "topo", tone: "rust" },
  privacy: { kind: "topo", tone: "sand" },
  done: { kind: "photo", src: "/images/IMG_8988.jpeg", position: "center 55%" },
};
const STEP_KEYS = Object.keys(VISUALS) as StepKey[];

function VisualPanel({ step }: { step: StepKey }) {
  return (
    <div className={styles.visual} aria-hidden="true">
      {STEP_KEYS.map((key) => {
        const visual = VISUALS[key];
        const active = key === step;
        return (
          <div key={key} className={styles.visualLayer} data-active={active || undefined}>
            {visual.kind === "photo" ? (
              <Image
                src={visual.src}
                alt=""
                fill
                sizes="(max-width: 899px) 100vw, 42vw"
                priority={active}
                className={styles.visualPhoto}
                style={{ objectPosition: visual.position }}
              />
            ) : (
              <div className={styles.visualTopo} data-tone={visual.tone}>
                <div className={styles.visualContours} />
              </div>
            )}
          </div>
        );
      })}
      <div className={styles.visualShade} />
    </div>
  );
}

// ---------------------------------------------------------------- the page

class StepProblem extends Error {}

const messageOf = (error: unknown) =>
  error instanceof Error && error.message ? error.message : "That didn't save. Check your connection and try again.";

/**
 * /welcome: loads what the flow needs (profile, saved answers, privacy), then
 * runs it. Signed-out visitors go to sign in; someone who already finished or
 * skipped it goes on to where they were heading.
 */
export default function WelcomeFlow() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNextPath(searchParams.get("next"));
  const { status, user } = useAuth();
  const { profile, error: profileError } = useProfile();
  const [loaded, setLoaded] = useState<{ userId: string; prefs: Preferences; privacy: PrivacySettings } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // Set once the flow is on screen, so finishing it doesn't bounce away mid-celebration.
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (status === "signedOut") router.replace("/login");
  }, [status, router]);

  const userId = user?.id ?? null;
  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    Promise.all([getPreferences(controller.signal), getPrivacy(controller.signal)])
      .then(([prefs, privacy]) => {
        setLoaded({ userId, prefs, privacy });
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setLoadError(messageOf(error));
      });
    return () => controller.abort();
  }, [userId, attempt]);

  const ready = profile && loaded && loaded.userId === profile.id;
  const alreadyDone = Boolean(ready && profile.username && !profile.onboarding_pending);

  useEffect(() => {
    if (alreadyDone && !started) router.replace(next);
  }, [alreadyDone, started, next, router]);

  if (ready && !alreadyDone && !started) setStarted(true);

  if (loadError || profileError) {
    return (
      <div className={styles.loading}>
        <p role="alert">{loadError ?? profileError}</p>
        <button type="button" className={ui.primary} onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  if (!ready || (alreadyDone && !started)) {
    return (
      <div className={styles.loading} role="status">
        <span className={styles.loadingLogo} aria-hidden="true" />
        <span>Getting things ready…</span>
      </div>
    );
  }
  return <Flow profile={profile} prefs={loaded.prefs} privacy={loaded.privacy} next={next} email={user?.email ?? null} />;
}

// ---------------------------------------------------------------- the flow

function Flow({
  profile,
  prefs,
  privacy,
  next,
  email,
}: {
  profile: Profile;
  prefs: Preferences;
  privacy: PrivacySettings;
  next: string;
  email: string | null;
}) {
  const router = useRouter();
  const [step, setStep] = useState<StepKey>(() => resumeStep(profile.username, prefs.onboarding.step));
  const [direction, setDirection] = useState<"forward" | "back">("forward");
  const [saving, setSaving] = useState<"continue" | "skip" | "skipAll" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  // Answers, starting from what's already saved.
  const [displayName, setDisplayName] = useState(profile.display_name ?? "");
  const [username, setUsername] = useState(profile.username ?? "");
  const usernameStatus = useUsernameStatus(username, profile.username);
  const [home, setHome] = useState<ProvinceCode | "none" | null>(profile.home_province ?? (prefs.onboarding.step ? "none" : null));
  const [showHome, setShowHome] = useState(privacy.show_home_province);
  const [style, setStyle] = useState<HikingStyle | null>(prefs.hiking_style);
  const [experience, setExperience] = useState<Experience | null>(prefs.experience);
  const [interests, setInterests] = useState<string[]>(prefs.interests);
  const [regions, setRegions] = useState<string[]>(prefs.favourite_regions);
  // Picks on the two history steps, saved when they continue (not when they skip).
  const [pastPicks, setPastPicks] = useState<Set<string>>(() => new Set());
  const [packPicks, setPackPicks] = useState<Map<string, ProductSummary>>(() => new Map());
  // One request id per product for the flow's life, so a retried Continue adds nothing twice.
  const packRequestIds = useRef(new Map<string, string>());
  const [units, setUnits] = useState<UnitSystem>(profile.units ?? "metric");
  const [isPrivate, setIsPrivate] = useState(privacy.is_private);
  const [savedPrivacy, setSavedPrivacy] = useState(privacy);

  // Every new screen: its heading takes focus (read out first), from the top.
  const firstScreen = useRef(true);
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
    if (!firstScreen.current) {
      window.scrollTo({ top: 0 });
      panelRef.current?.scrollTo({ top: 0 });
    }
    firstScreen.current = false;
  }, [step]);

  const go = (target: StepKey, way: "forward" | "back") => {
    setDirection(way);
    setStep(target);
    setError(null);
    setSubmitted(false);
  };

  /** Saves this screen's answers; returns any that live with the preferences. */
  const saveAnswers = async (): Promise<PreferencesUpdate> => {
    switch (step) {
      case "name": {
        const name = displayName.trim().replace(/\s+/g, " ");
        if (!name) throw new StepProblem("Add the name you'd like to go by.");
        if (!usernameReady(usernameStatus)) {
          throw new StepProblem(
            usernameStatus.state === "checking" ? "Still checking that username. Try again in a moment." : usernameStatus.message,
          );
        }
        const update: ProfileUpdate = {};
        if (name !== profile.display_name) update.display_name = name;
        const chosen = normalizeUsername(username);
        if (chosen !== profile.username) update.username = chosen;
        if (Object.keys(update).length) announceProfile(await updateProfile(update));
        return {};
      }
      case "home": {
        const code = home === "none" ? null : home;
        if (home !== null && code !== profile.home_province) announceProfile(await updateProfile({ home_province: code }));
        const show = code ? showHome : false;
        if (show !== savedPrivacy.show_home_province) setSavedPrivacy(await updatePrivacy({ show_home_province: show }));
        return {};
      }
      case "style":
        return { hiking_style: style };
      case "experience":
        return { experience };
      case "interests":
        return { interests };
      case "regions":
        return { favourite_regions: regions };
      case "hiked":
        if (pastPicks.size > 0) {
          await addPastHikes([...pastPicks]);
          setPastPicks(new Set());
        }
        return {};
      case "pack": {
        const left = new Map(packPicks);
        try {
          for (const product of packPicks.values()) {
            let requestId = packRequestIds.current.get(product.id);
            if (!requestId) {
              requestId = crypto.randomUUID();
              packRequestIds.current.set(product.id, requestId);
            }
            await addMyGear({ product_id: product.id, client_request_id: requestId });
            left.delete(product.id);
          }
        } finally {
          setPackPicks(left);
        }
        return {};
      }
      case "units":
        if (units !== profile.units) announceProfile(await updateProfile({ units }));
        return {};
      case "privacy":
        if (isPrivate !== savedPrivacy.is_private) setSavedPrivacy(await updatePrivacy({ is_private: isPrivate }));
        return {};
      default:
        return {};
    }
  };

  /** Records the move (and any answers) so leaving and coming back resumes here. */
  const advance = async (answers: PreferencesUpdate) => {
    const target = nextStep(step);
    const finishing = target === "done";
    await updatePreferences({ ...answers, onboarding_step: target, ...(finishing ? { onboarding_status: "completed" } : {}) });
    if (finishing) announceProfile(await getProfile());
    go(target, "forward");
  };

  const onContinue = async () => {
    if (saving) return;
    setSubmitted(true);
    setSaving("continue");
    setError(null);
    try {
      await advance(await saveAnswers());
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setSaving(null);
    }
  };

  const onSkip = async () => {
    if (saving) return;
    setSaving("skip");
    setError(null);
    try {
      await advance({});
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setSaving(null);
    }
  };

  const onBack = () => {
    const previous = previousStep(step);
    if (!previous) return;
    go(previous, "back");
    updatePreferences({ onboarding_step: previous }).catch(() => undefined);
  };

  const onSkipAll = async () => {
    if (saving) return;
    setSaving("skipAll");
    setError(null);
    try {
      await updatePreferences({ onboarding_step: step, onboarding_status: "skipped" });
      announceProfile(await getProfile());
      router.replace(next);
    } catch (caught) {
      setError(messageOf(caught));
      setSaving(null);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    // Forms in dialogs (the photo cropper) bubble through React portals; only ours continues.
    if (event.target !== event.currentTarget || step === "done") return;
    void onContinue();
  };

  // Enter continues from a card or chip too, not just from a text box.
  const onKeyDown = (event: KeyboardEvent<HTMLFormElement>) => {
    const target = event.target as HTMLElement;
    if (event.key !== "Enter" || !(target instanceof HTMLInputElement)) return;
    if (target.type === "radio" || target.type === "checkbox") {
      event.preventDefault();
      event.currentTarget.requestSubmit();
    }
  };

  const number = stepNumber(step);
  const done = step === "done";
  const canSkipAll = Boolean(profile.username) && !done;
  const previous = previousStep(step);
  const firstName = (profile.display_name ?? displayName).trim().split(/\s+/)[0] || profile.username || "friend";

  const screen = SCREENS[step]({
    firstName,
    profile,
    email,
    next,
    // Editing the name or username clears the last "can't continue" message.
    nameStep: {
      displayName,
      setDisplayName: (value: string) => {
        setDisplayName(value);
        setError(null);
      },
      username,
      setUsername: (value: string) => {
        setUsername(value);
        setError(null);
      },
      usernameStatus,
      submitted,
    },
    homeStep: { home, setHome, showHome, setShowHome },
    style,
    setStyle,
    experience,
    setExperience,
    interests,
    setInterests,
    regions,
    setRegions,
    home: home === "none" ? null : home,
    pastPicks,
    togglePast: (trailId: string) =>
      setPastPicks((current) => {
        const next = new Set(current);
        if (next.has(trailId)) next.delete(trailId);
        else next.add(trailId);
        return next;
      }),
    packPicks,
    togglePack: (product: ProductSummary) =>
      setPackPicks((current) => {
        const next = new Map(current);
        if (next.has(product.id)) next.delete(product.id);
        else next.set(product.id, product);
        return next;
      }),
    units,
    setUnits,
    isPrivate,
    setIsPrivate,
  });

  return (
    <div className={styles.page}>
      <div
        className={styles.progress}
        role="progressbar"
        aria-label="Setup progress"
        aria-valuemin={0}
        aria-valuemax={QUESTION_COUNT}
        aria-valuenow={done ? QUESTION_COUNT : number}
        aria-valuetext={done ? "All steps done" : `Step ${number} of ${QUESTION_COUNT}`}
      >
        <div className={styles.progressFill} style={{ width: `${((done ? QUESTION_COUNT : number) / QUESTION_COUNT) * 100}%` }} />
      </div>

      <VisualPanel step={step} />
      <span className={styles.logo} role="img" aria-label="Trekly" />

      <main className={styles.panel} ref={panelRef}>
        <header className={styles.bar}>
          <p className={styles.counter} aria-hidden="true">
            {done ? "All done" : `Step ${number} of ${QUESTION_COUNT}`}
          </p>
          {canSkipAll && (
            <button type="button" className={styles.skipAll} onClick={onSkipAll} disabled={saving !== null}>
              {saving === "skipAll" ? "Leaving…" : "Skip for now"}
            </button>
          )}
        </header>

        <form className={styles.form} onSubmit={onSubmit} onKeyDown={onKeyDown} noValidate aria-labelledby="welcome-heading">
          <div key={step} className={styles.screen} data-direction={direction}>
            <h1 id="welcome-heading" ref={headingRef} tabIndex={-1} className={styles.heading}>
              {screen.title}
            </h1>
            {screen.lead && <p className={styles.lead}>{screen.lead}</p>}
            <div className={styles.body}>{screen.body}</div>
          </div>

          {!done && (
            <div className={styles.actions}>
              {error && (
                <p className={`${ui.error} ${styles.actionError}`} role="alert">
                  {error}
                </p>
              )}
              <div className={styles.actionRow}>
                {previous && (
                  <button type="button" className={styles.back} onClick={onBack} disabled={saving !== null}>
                    <ArrowLeft size={18} aria-hidden="true" />
                    Back
                  </button>
                )}
                <span className={styles.spacer} />
                {isOptional(step) && (
                  <button type="button" className={styles.skip} onClick={onSkip} disabled={saving !== null}>
                    {saving === "skip" ? "Skipping…" : "Skip"}
                  </button>
                )}
                <button type="submit" className={styles.continue} disabled={saving !== null}>
                  {saving === "continue" ? "Saving…" : step === "privacy" ? "Finish" : "Continue"}
                  <ArrowRight size={18} aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </form>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------- screens

interface ScreenProps {
  firstName: string;
  profile: Profile;
  email: string | null;
  next: string;
  nameStep: {
    displayName: string;
    setDisplayName: (value: string) => void;
    username: string;
    setUsername: (value: string) => void;
    usernameStatus: ReturnType<typeof useUsernameStatus>;
    submitted: boolean;
  };
  homeStep: {
    home: ProvinceCode | "none" | null;
    setHome: (value: ProvinceCode | "none") => void;
    showHome: boolean;
    setShowHome: (value: boolean) => void;
  };
  style: HikingStyle | null;
  setStyle: (value: HikingStyle) => void;
  experience: Experience | null;
  setExperience: (value: Experience) => void;
  interests: string[];
  setInterests: (value: string[]) => void;
  regions: string[];
  setRegions: (value: string[]) => void;
  home: ProvinceCode | null;
  pastPicks: ReadonlySet<string>;
  togglePast: (trailId: string) => void;
  packPicks: ReadonlyMap<string, ProductSummary>;
  togglePack: (product: ProductSummary) => void;
  units: UnitSystem;
  setUnits: (value: UnitSystem) => void;
  isPrivate: boolean;
  setIsPrivate: (value: boolean) => void;
}

interface Screen {
  title: string;
  lead?: ReactNode;
  body: ReactNode;
}

const SCREENS: Record<StepKey, (props: ScreenProps) => Screen> = {
  name: ({ nameStep, profile, email }) => ({
    title: "What should we call you?",
    lead: "Your name shows on your profile. Your username is its address, like /u/your_name.",
    body: <NameStep {...nameStep} profile={profile} email={email} />,
  }),
  photo: ({ profile }) => ({
    title: "Put a face to the name",
    lead: "Add a profile photo so fellow hikers know it's you. Your initials show until you do.",
    body: <PhotoStep profile={profile} />,
  }),
  home: ({ homeStep }) => ({
    title: "Where do you call home?",
    lead: "Pick your province or territory to earn its badge.",
    body: <HomeStep {...homeStep} />,
  }),
  style: ({ style, setStyle }) => ({
    title: "How do you like to hike?",
    lead: "We'll lean your trail picks this way.",
    body: (
      <HikingStyleCards
        value={style}
        onChange={setStyle}
        icons={{ day: <Sun size={22} />, overnight: <Tent size={22} />, both: <Backpack size={22} /> }}
      />
    ),
  }),
  experience: ({ experience, setExperience }) => ({
    title: "How much trail time do you have?",
    lead: "So the trails we suggest match your legs. No judgement.",
    body: (
      <ExperienceCards
        value={experience}
        onChange={setExperience}
        icons={{ new: <Sprout size={22} />, few_seasons: <Footprints size={22} />, seasoned: <Mountain size={22} /> }}
      />
    ),
  }),
  interests: ({ interests, setInterests }) => ({
    title: "What gets you out there?",
    lead: "Pick as many as you like.",
    body: <InterestChips values={interests} onChange={setInterests} />,
  }),
  regions: ({ regions, setRegions }) => ({
    title: "Which places are on your radar?",
    lead: "Pick the parks you'd love to explore. They'll come first when you open Explore.",
    body: <RegionPicker values={regions} onChange={setRegions} />,
  }),
  hiked: ({ home, regions, pastPicks, togglePast }) => ({
    title: "Which of these have you hiked?",
    lead: "Tap any you've done. They go in your Trail Journal, and you can add dates later.",
    body: <HikedStep home={home} regions={regions} selected={pastPicks} onToggle={togglePast} />,
  }),
  pack: ({ packPicks, togglePack }) => ({
    title: "What's in your pack?",
    lead: "Tap the gear you own to add it to your kit. You can skip this and add gear any time.",
    body: <PackStep selected={packPicks} onToggle={togglePack} />,
  }),
  units: ({ units, setUnits }) => ({
    title: "Metric or imperial?",
    lead: "How distances, elevations and gear weights read across Trekly.",
    body: (
      <ChoiceCards
        legend="Units"
        columns={2}
        value={units}
        onChange={setUnits}
        options={(["metric", "imperial"] as const).map((system) => ({
          value: system,
          label: system === "metric" ? "Metric" : "Imperial",
          hint: system === "metric" ? "Kilometres, metres and kilograms." : "Miles, feet and pounds.",
          icon: <Ruler size={22} />,
          extra: (
            <span className={styles.sample}>
              e.g. {formatDistance(12.4, system)} · {formatElevation(850, system)} gain
            </span>
          ),
        }))}
      />
    ),
  }),
  privacy: ({ isPrivate, setIsPrivate }) => ({
    title: "Who can see your profile?",
    lead: "You can change this any time.",
    body: (
      <>
        <ChoiceCards
          legend="Profile visibility"
          columns={2}
          value={isPrivate ? "private" : "public"}
          onChange={(value) => setIsPrivate(value === "private")}
          options={[
            {
              value: "public",
              label: "Public",
              hint: "Anyone with the link sees your profile, showing only the sections you choose.",
              icon: <Globe size={22} />,
            },
            {
              value: "private",
              label: "Private",
              hint: "Only you see your profile. Your journal, gear and plans stay yours.",
              icon: <Lock size={22} />,
            },
          ]}
        />
        <p className={styles.note}>
          Pick exactly which sections show in <Link href="/settings/privacy">Privacy settings</Link>.
        </p>
      </>
    ),
  }),
  done: ({ firstName, next }) => ({
    title: `You're all set, ${firstName}!`,
    lead: "Here are a few trails we think you'll love. Save any that catch your eye.",
    body: <FinishStep next={next} />,
  }),
};

// --------------------------------------------------------------- step bodies

function NameStep({
  displayName,
  setDisplayName,
  username,
  setUsername,
  usernameStatus,
  submitted,
  profile,
  email,
}: ScreenProps["nameStep"] & { profile: Profile; email: string | null }) {
  const nameId = useId();
  const missingName = submitted && !displayName.trim();
  return (
    <div className={styles.fields}>
      <label className={ui.field} htmlFor={nameId}>
        <span className={ui.label}>Your name</span>
        <input
          id={nameId}
          className={`${ui.input} ${styles.bigInput}`}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          autoComplete="name"
          maxLength={60}
          required
          aria-invalid={missingName}
          aria-describedby={`${nameId}-hint`}
        />
        <span id={`${nameId}-hint`} className={missingName ? ui.fieldError : ui.hint}>
          {missingName ? "Add the name you'd like to go by." : "Your first name is fine, or a trail name."}
        </span>
      </label>
      <UsernameField
        id="welcome-username"
        value={username}
        onChange={setUsername}
        status={usernameStatus}
        // Suggest from the name once there's one, else the email; never over a username they already have.
        suggestFrom={profile.username ? "" : suggestionHint(displayName, email)}
        showError={submitted}
      />
    </div>
  );
}

function PhotoStep({ profile }: { profile: Profile }) {
  const photo = useProfilePhoto(profile, { size: 160, alt: "Your profile photo" });
  return (
    <div className={styles.photoStep}>
      {photo.avatar}
      <button type="button" className={ui.secondary} onClick={photo.open} disabled={photo.busy}>
        {photo.hasPhoto ? "Change photo" : "Upload a photo"}
      </button>
      {photo.status}
    </div>
  );
}

const PROVINCE_ORDER: ProvinceCode[] = ["BC", "AB", "SK", "MB", "ON", "QC", "NB", "NS", "PE", "NL", "YT", "NT", "NU"];

function HomeStep({ home, setHome, showHome, setShowHome }: ScreenProps["homeStep"]) {
  const name = useId();
  const switchId = useId();
  const picked = home && home !== "none" ? provinceByCode(home) : null;
  const options = PROVINCE_ORDER.map((code) => PROVINCES.find((p) => p.code === code)!);
  return (
    <div className={styles.home}>
      <fieldset className={styles.provinceSet}>
        <legend className={ui.srOnly}>Province or territory</legend>
        <div className={styles.provinces}>
          {options.map((p) => (
            <label key={p.code} className={styles.province} data-checked={home === p.code || undefined}>
              <input
                type="radio"
                name={name}
                value={p.code}
                checked={home === p.code}
                onChange={() => setHome(p.code)}
                className={styles.hiddenInput}
              />
              <ProvinceBadge province={p} decorative className={styles.provinceBadge} />
              <span className={styles.provinceName}>{p.name}</span>
            </label>
          ))}
          <label className={`${styles.province} ${styles.provinceNone}`} data-checked={home === "none" || undefined}>
            <input
              type="radio"
              name={name}
              value="none"
              checked={home === "none"}
              onChange={() => setHome("none")}
              className={styles.hiddenInput}
            />
            <span className={styles.provinceName}>Prefer not to say</span>
          </label>
        </div>
      </fieldset>

      <div className={styles.earn} aria-live="polite">
        {picked ? (
          <>
            <ProvinceBadge province={picked} className={styles.earnBadge} />
            <div className={styles.earnText}>
              <p className={styles.earnTitle}>You&apos;ll earn the {picked.name} badge</p>
              <p className={ui.hint}>It sits with your milestones as your {homeLabel(picked).toLowerCase()}.</p>
            </div>
          </>
        ) : (
          <p className={ui.hint}>
            {home === "none" ? "No problem. You can add it later in Settings." : "Pick one above to see the badge you'll earn."}
          </p>
        )}
      </div>

      <label className={styles.switchRow} htmlFor={switchId} data-disabled={!picked || undefined}>
        <span className={styles.switchText}>
          <span className={styles.switchLabel}>Show on my profile</span>
          <span className={ui.hint} id={`${switchId}-hint`}>
            Off by default: only you see your home {picked?.kind ?? "province"} until you turn this on.
          </span>
        </span>
        <input
          id={switchId}
          type="checkbox"
          role="switch"
          className={styles.switch}
          checked={Boolean(picked) && showHome}
          disabled={!picked}
          onChange={(event) => setShowHome(event.target.checked)}
          aria-describedby={`${switchId}-hint`}
        />
      </label>
    </div>
  );
}

function FinishStep({ next }: { next: string }) {
  const [picks, setPicks] = useState<TrailListItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const saved = useSavedTrails();
  const { profile } = useProfile();
  const units: UnitSystem = profile?.units ?? "metric";

  useEffect(() => {
    const controller = new AbortController();
    getRecommendations(5, controller.signal)
      .then(setPicks)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, []);

  const back = next !== DEFAULT_AFTER_LOGIN ? { href: next, label: "Back to where you were" } : { href: "/profile", label: "Go to my profile" };

  return (
    <div className={styles.finish}>
      <div className={styles.burst} aria-hidden="true">
        {Array.from({ length: 14 }, (_, index) => (
          <span key={index} style={{ "--i": index } as React.CSSProperties} />
        ))}
      </div>

      {picks === null && !failed && (
        <ul className={styles.picks} aria-busy="true" aria-label="Loading trail picks">
          {[0, 1, 2].map((key) => (
            <li key={key} className={`${styles.pick} ${ui.skeleton}`} />
          ))}
        </ul>
      )}
      {failed && <p className={ui.hint}>We couldn&apos;t load your picks just now, but Explore has every trail.</p>}
      {picks && picks.length > 0 && (
        <ul className={styles.picks} aria-label="Trails picked for you">
          {picks.map((trail) => {
            const distance = formatTrailDistance(trail.distance_km, trail.route_type, units);
            return (
              <li key={trail.id} className={styles.pick}>
                <Link href={`/trails?id=${encodeURIComponent(trail.id)}`} className={styles.pickLink}>
                  <TrailPhoto photo={trail.photo} name={trail.name} variant="thumb" />
                  <span className={styles.pickText}>
                    <span className={styles.pickName}>{trail.name}</span>
                    <span className={styles.pickMeta}>
                      {[trail.park_name ?? trail.region, TERRAIN_LABELS[trail.terrain], distance].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </Link>
                <SaveTrailButton
                  trailId={trail.id}
                  trailName={trail.name}
                  saved={saved.savedIds.has(trail.id)}
                  pending={saved.pending.has(trail.id)}
                  onToggle={saved.toggle}
                  returnTo="/welcome"
                  compact
                />
              </li>
            );
          })}
        </ul>
      )}

      <div className={styles.finishActions}>
        <Link href={EXPLORE_HREF} className={styles.continue}>
          <Compass size={18} aria-hidden="true" />
          Explore all trails
        </Link>
        <Link href={back.href} className={styles.back}>
          {back.label}
        </Link>
      </div>
      <p className={styles.note}>You can change any of your answers later in Settings.</p>
    </div>
  );
}
