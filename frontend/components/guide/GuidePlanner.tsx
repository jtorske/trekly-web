"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import Dialog from "@/components/Dialog";
import SaveTrailButton from "@/components/SaveTrailButton";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import {
  answerLabel,
  isoDate,
  nextStep,
  summary,
  toRequest,
  type PlannerAnswers,
  type PlannerContext,
  type Step,
} from "@/lib/guide";
import { getGuideProfile, recommendTrails, type Recommendation, type RecommendResponse } from "@/lib/guideApi";
import { trailHref } from "@/lib/site";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import { formatTrailDistance, formatTrailElevation } from "@/lib/units";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { useUnits } from "@/lib/useUnits";
import styles from "./GuidePlanner.module.css";

/** How long Trekly "types" before a question appears. */
const TYPING_MS = 450;

export function GuideAvatar({ size = "md" }: { size?: "sm" | "md" }) {
  return (
    <span className={`${styles.avatar} ${size === "sm" ? styles.avatarSm : ""}`} aria-hidden="true">
      <Compass strokeWidth={1.8} />
    </span>
  );
}

export function Typing() {
  return (
    <div className={styles.guideRow}>
      <GuideAvatar size="sm" />
      <div className={`${styles.bubble} ${styles.typing}`} role="status" aria-label="Trekly Guide is typing">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

export function GuideSays({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${styles.guideRow} ${styles.enter}`}>
      <GuideAvatar size="sm" />
      <div className={styles.bubble}>{children}</div>
    </div>
  );
}

export function YouSaid({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${styles.youRow} ${styles.enter}`}>
      <div className={`${styles.bubble} ${styles.you}`}>
        <span className={ui.srOnly}>You: </span>
        {children}
      </div>
    </div>
  );
}

/** avalanche.ca as a link inside a reason. */
export function LinkedText({ text }: { text: string }) {
  // One inline span: the chat bubble lays its children out as a column.
  return (
    <span>
      {text.split(/(https:\/\/avalanche\.ca)/).map((part, index) =>
        part === "https://avalanche.ca" ? (
          <a key={index} href={part} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
            avalanche.ca
          </a>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </span>
  );
}

export function ResultCard({
  pick,
  returnTo,
}: {
  pick: Pick<Recommendation, "trail" | "reasons" | "est_label" | "dog_note" | "dog_policy">;
  returnTo: string;
}) {
  const [units] = useUnits();
  const saved = useSavedTrails();
  const { trail } = pick;
  const meta = [
    trail.typical_duration_nights ? tripLengthLabel(trail.typical_duration_nights) : null,
    formatTrailDistance(trail.distance_km, trail.route_type, units),
    trail.elevation_gain_m != null ? `${formatTrailElevation(trail.elevation_gain_m, units)} gain` : null,
  ].filter(Boolean);
  return (
    <li className={`${styles.card} ${styles.enter}`}>
      <div className={styles.cardPhoto}>
        <TrailPhoto photo={trail.photo ?? null} routeMap={trail.route_map ?? null} name={trail.name} variant="thumb" />
      </div>
      <div className={styles.cardBody}>
        <h3 className={styles.cardName}>
          <Link href={trailHref(trail)} className={styles.cardLink}>
            {trail.name}
          </Link>
        </h3>
        <p className={styles.cardRegion}>{trail.region}</p>
        <p className={styles.cardMeta}>
          <span>{TERRAIN_LABELS[trail.terrain]}</span>
          {meta.map((item) => (
            <span key={item}>{item}</span>
          ))}
          {pick.est_label && <span>About {pick.est_label}{trail.typical_duration_nights ? " a day" : ""} for you</span>}
        </p>
        <ul className={styles.reasons}>
          {pick.reasons.map((reason) => (
            <li key={reason}>
              <LinkedText text={reason} />
            </li>
          ))}
        </ul>
        {pick.dog_note && (
          <p className={pick.dog_policy === "on_leash" ? styles.dogOk : styles.dogCheck}>{pick.dog_note}</p>
        )}
      </div>
      <div className={styles.cardSave}>
        <SaveTrailButton
          trailId={trail.id}
          trailName={trail.name}
          saved={saved.savedIds.has(trail.id)}
          pending={saved.pending.has(trail.id)}
          onToggle={saved.toggle}
          returnTo={returnTo}
          compact
        />
      </div>
    </li>
  );
}

function DatePick({ onPick, today }: { onPick: (value: string) => void; today: Date }) {
  const id = useId();
  const min = isoDate(today);
  const max = isoDate(new Date(today.getFullYear() + 1, today.getMonth(), today.getDate()));
  const [value, setValue] = useState(min);
  return (
    <form
      className={styles.datePick}
      onSubmit={(event) => {
        event.preventDefault();
        if (value) onPick(value);
      }}
    >
      <label htmlFor={id} className={ui.srOnly}>
        Date
      </label>
      <input
        id={id}
        type="date"
        className={ui.input}
        min={min}
        max={max}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        data-autofocus
      />
      <button type="submit" className={ui.primary}>
        Use this date
      </button>
    </form>
  );
}

function Chips({ step, onAnswer, today }: { step: Step; onAnswer: (value: string) => void; today: Date }) {
  const [picking, setPicking] = useState(false);
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    first.current?.focus({ preventScroll: true });
  }, [step.key]);
  if (picking) return <DatePick onPick={onAnswer} today={today} />;
  return (
    <div className={`${styles.chips} ${styles.enter}`} role="group" aria-label={step.question}>
      {step.choices.map((choice, index) => (
        <button
          key={choice.value}
          ref={index === 0 ? first : undefined}
          type="button"
          className={styles.chip}
          onClick={() => (choice.value === "pick" ? setPicking(true) : onAnswer(choice.value))}
        >
          <span>{choice.label}</span>
          {choice.hint && <span className={styles.chipHint}>{choice.hint}</span>}
        </button>
      ))}
    </div>
  );
}

type Phase = { kind: "asking" } | { kind: "loading" } | { kind: "done"; response: RecommendResponse } | { kind: "error"; message: string };

/**
 * "Plan with Trekly Guide": a few quick questions, one at a time, then three
 * trails with reasons. Everything comes from the deterministic engine
 * (POST /api/guide/recommend); nothing is stored.
 */
export default function GuidePlanner({ onClose, intro }: { onClose: () => void; intro?: string }) {
  const { status } = useAuth();
  const signedIn = status === "signedIn";
  const pathname = usePathname() ?? "/";
  const today = useMemo(() => new Date(), []);
  // What Trekly already knows when signed in: home province, dog default,
  // whether to ask their experience. Guests are always asked.
  const [known, setKnown] = useState<PlannerContext | null>(null);
  const guest = useMemo<PlannerContext>(() => ({ askExperience: true, homeProvince: null, today }), [today]);
  const context = status === "loading" ? null : signedIn ? known : guest;
  const [answers, setAnswers] = useState<PlannerAnswers>({});
  const [history, setHistory] = useState<{ step: Step; value: string }[]>([]);
  // The question Trekly has finished "typing" (a short pause before each one).
  const [typedKey, setTypedKey] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "asking" });
  const [picks, setPicks] = useState<Recommendation[]>([]);
  const [shown, setShown] = useState<string[]>([]);
  const [more, setMore] = useState<"idle" | "loading" | "none">("idle");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    getGuideProfile(controller.signal)
      .then((profile) =>
        setKnown({
          askExperience: profile.experience.basis === "stated" && !profile.preferences.experience_level,
          homeProvince: profile.home_province,
          dogByDefault: profile.preferences.hikes_with_dog,
          today,
        }),
      )
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setKnown({ askExperience: true, homeProvince: null, today });
      });
    return () => controller.abort();
  }, [signedIn, today]);

  const step = context ? nextStep(answers, context) : null;
  const stepKey = step ? `${history.length}:${step.key}` : null;
  const typing = stepKey !== null && typedKey !== stepKey;

  useEffect(() => {
    if (!stepKey) return;
    const timer = window.setTimeout(() => setTypedKey(stepKey), TYPING_MS);
    return () => window.clearTimeout(timer);
  }, [stepKey]);

  // Keep the newest message in view.
  useEffect(() => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ block: "end", behavior: still ? "auto" : "smooth" });
  }, [history.length, typing, phase.kind, picks.length]);

  /** Everything answered: ask the engine. */
  const search = (final: PlannerAnswers) => {
    setPhase({ kind: "loading" });
    recommendTrails(toRequest(final, today), signedIn)
      .then((response) => {
        setPicks(response.results);
        setShown(response.results.map((r) => r.trail.id));
        setMore("idle");
        setPhase({ kind: "done", response });
      })
      .catch((error: unknown) =>
        setPhase({ kind: "error", message: error instanceof Error ? error.message : "Something went wrong." }),
      );
  };

  const answer = (value: string) => {
    if (!step || !context) return;
    const next = { ...answers, [step.key]: value };
    setHistory((items) => [...items, { step, value }]);
    setAnswers(next);
    if (!nextStep(next, context)) search(next);
  };

  const back = () => {
    const last = history[history.length - 1];
    if (!last) return;
    setHistory((items) => items.slice(0, -1));
    setAnswers((current) => {
      const copy = { ...current };
      delete copy[last.step.key];
      return copy;
    });
    setPhase({ kind: "asking" });
    setPicks([]);
    setShown([]);
    setMore("idle");
  };

  const restart = () => {
    setHistory([]);
    setAnswers({});
    setPhase({ kind: "asking" });
    setPicks([]);
    setShown([]);
    setMore("idle");
  };

  const showMore = async () => {
    setMore("loading");
    try {
      const response = await recommendTrails(toRequest(answers, today, shown), signedIn);
      if (response.results.length === 0) {
        setMore("none");
        return;
      }
      setPicks((current) => [...current, ...response.results]);
      setShown((ids) => [...ids, ...response.results.map((r) => r.trail.id)]);
      setMore(response.results.length < 3 ? "none" : "idle");
    } catch {
      setMore("idle");
    }
  };

  const done = phase.kind === "done" ? phase.response : null;
  const composer = (
    <div className={styles.composer}>
      {context && step && !typing && <Chips key={step.key} step={step} onAnswer={answer} today={today} />}
      {done && (
        <div className={styles.actions}>
          {picks.length > 0 && more !== "none" && (
            <button type="button" className={ui.primary} onClick={showMore} disabled={more === "loading"}>
              {more === "loading" ? "Finding more…" : "Show me more"}
            </button>
          )}
          <button type="button" className={ui.secondary} onClick={restart}>
            Start over
          </button>
        </div>
      )}
      {history.length > 0 && phase.kind !== "loading" && (
        <button type="button" className={styles.linkButton} onClick={back}>
          ← Change my last answer
        </button>
      )}
    </div>
  );

  return (
    <Dialog
      title="Trekly Guide"
      subtitle="A few quick questions, then trails picked for you"
      onClose={onClose}
      sheet
      size="md"
      footer={composer}
    >
      <div className={styles.planner}>
        <div className={styles.log} role="log" aria-live="polite" aria-label="Conversation with Trekly Guide">
          {intro && <GuideSays>{intro}</GuideSays>}
          <GuideSays>
            Hi! I&apos;ll find a few trails that fit you.
            {signedIn ? " I'll use your Trail Journal unless you've turned that off in Settings." : ""}
          </GuideSays>
          {history.map(({ step: asked, value }) => (
            <div key={asked.key} className={styles.pair}>
              <GuideSays>{asked.question}</GuideSays>
              <YouSaid>{answerLabel(asked, value)}</YouSaid>
            </div>
          ))}

          {!context || (step && typing) ? <Typing /> : null}
          {context && step && !typing && <GuideSays>{step.question}</GuideSays>}

          {phase.kind === "loading" && <Typing />}
          {phase.kind === "error" && (
            <GuideSays>
              <span className={styles.error}>{phase.message}</span>{" "}
              <button type="button" className={styles.linkButton} onClick={() => search(answers)}>
                Try again
              </button>
            </GuideSays>
          )}
          {done && (
            <>
              <GuideSays>
                {picks.length > 0
                  ? `Here ${picks.length === 1 ? "is a trail" : `are ${picks.length} trails`} for ${summary(answers, today)}.`
                  : "I couldn't find a trail that fits all of that."}
                {done.notes.map((note) => (
                  <span key={note} className={styles.note}>
                    {note}
                  </span>
                ))}
                {done.basis === "stated" && signedIn && picks.length > 0 && (
                  <span className={styles.note}>
                    Log a few past hikes (with times) and these get more personal.
                  </span>
                )}
              </GuideSays>
              {picks.length > 0 && (
                <ul className={styles.cards} aria-label="Recommended trails">
                  {picks.map((pick) => (
                    <ResultCard key={pick.trail.id} pick={pick} returnTo={pathname} />
                  ))}
                </ul>
              )}
              {more === "none" && picks.length > 0 && <GuideSays>That&apos;s everything that fits for now.</GuideSays>}
            </>
          )}
          <div ref={endRef} />
        </div>

      </div>
    </Dialog>
  );
}
