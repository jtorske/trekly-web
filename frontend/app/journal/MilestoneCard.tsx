"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { formatHikeDate } from "@/lib/publicProfile";
import { earnedSummary, earnedWhen, milestoneDetail, progressFraction, progressLabel, TIER_NAMES, type Milestone, type Tier } from "@/lib/milestones";
import type { UnitSystem } from "@/lib/units";
import styles from "./MilestoneCard.module.css";

const GAP = 8;
const MARGIN = 8;

/**
 * A medal that explains itself. Hovering it (with a mouse), focusing it from
 * the keyboard, or tapping it shows a card: for an earned milestone, a check,
 * how it was earned, the day and the tier; for the rest, what it takes and
 * how far along it is. A tap or click pins the card until the next tap,
 * Escape, or a tap elsewhere.
 *
 * The card is portalled to the body with fixed positioning: the book's pages
 * clip their contents and are transformed while they turn.
 */
export default function MilestoneCard({
  milestone,
  units,
  tierPoints,
  className = "",
  children,
}: {
  milestone: Milestone;
  units: UnitSystem;
  tierPoints?: Record<Tier, number>;
  className?: string;
  /** The medal art. */
  children: ReactNode;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hovered || focused || pinned;

  const close = useCallback(() => {
    setHovered(false);
    setFocused(false);
    setPinned(false);
  }, []);

  // Above the medal if it fits, else below; kept inside the viewport. Set
  // straight on the element: it's measured, so it can only happen after render.
  const place = useCallback(() => {
    const button = trigger.current;
    const box = card.current;
    if (!button || !box) return;
    const anchor = button.getBoundingClientRect();
    const { width, height } = box.getBoundingClientRect();
    const below = anchor.top - GAP - height < MARGIN;
    const top = below ? Math.min(anchor.bottom + GAP, window.innerHeight - height - MARGIN) : anchor.top - GAP - height;
    const centre = anchor.left + anchor.width / 2 - width / 2;
    const left = Math.max(MARGIN, Math.min(centre, window.innerWidth - width - MARGIN));
    box.style.left = `${left}px`;
    box.style.top = `${Math.max(MARGIN, top)}px`;
    box.toggleAttribute("data-below", below);
    box.style.visibility = "visible";
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Only this card closes; nothing else (a dialog, the book) hears it.
        event.stopPropagation();
        close();
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !card.current?.contains(event.target as Node)) close();
    };
    window.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, close, place]);

  const hidden = milestone.secret && !milestone.earned;
  const name = hidden ? "the secret milestone" : milestone.title;

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={`${styles.trigger} ${className}`}
        aria-label={`Details for ${name}`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onPointerEnter={(event) => event.pointerType === "mouse" && setHovered(true)}
        onPointerLeave={(event) => event.pointerType === "mouse" && setHovered(false)}
        onFocus={(event) => setFocused(event.currentTarget.matches(":focus-visible"))}
        onBlur={close}
        onClick={() => setPinned((was) => !was)}
      >
        {children}
      </button>
      {open &&
        createPortal(
          <div
            ref={card}
            id={id}
            role="tooltip"
            className={styles.card}
            data-earned={milestone.earned || undefined}
            style={{ left: 0, top: 0, visibility: "hidden" }}
            onPointerEnter={(event) => event.pointerType === "mouse" && setHovered(true)}
            onPointerLeave={(event) => event.pointerType === "mouse" && setHovered(false)}
          >
            <CardBody milestone={milestone} units={units} tierPoints={tierPoints} />
          </div>,
          document.body,
        )}
    </>
  );
}

function CardBody({ milestone, units, tierPoints }: { milestone: Milestone; units: UnitSystem; tierPoints?: Record<Tier, number> }) {
  const tier = milestone.tier ? TIER_NAMES[milestone.tier] : null;
  const points = milestone.tier && tierPoints ? tierPoints[milestone.tier] : null;
  const tierLine = tier && (
    <span className={styles.tier} data-tier={milestone.tier}>
      {tier} tier{points != null && <> · +{points} pts</>}
    </span>
  );

  if (milestone.earned) {
    const when = earnedWhen(milestone, formatHikeDate);
    return (
      <>
        <p className={styles.status}>
          <svg viewBox="0 0 24 24" className={styles.check} aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <path d="m7.5 12.5 3 3 6-7" />
          </svg>
          Earned
        </p>
        <p className={styles.title}>{milestone.title}</p>
        <p className={styles.how}>{earnedSummary(milestone, units)}</p>
        <p className={styles.meta}>
          {when && <span>{when}</span>}
          {tierLine}
        </p>
      </>
    );
  }

  const hidden = milestone.secret;
  const progress = progressLabel(milestone, units);
  return (
    <>
      <p className={styles.status}>
        <span className={styles.open} aria-hidden="true" />
        {hidden ? "Secret milestone" : "Not earned yet"}
      </p>
      <p className={styles.title}>{milestone.title}</p>
      <p className={styles.how}>{hidden ? `Hint: ${milestone.detail}` : milestoneDetail(milestone, units)}</p>
      {milestone.note && <p className={styles.note}>{milestone.note}</p>}
      {milestone.needs_data && (
        <p className={styles.note}>Needs more trail data: not enough catalogue trails have this measured yet.</p>
      )}
      {progress && !milestone.needs_data && (
        <p className={styles.progress}>
          <span className={styles.bar} aria-hidden="true">
            <span style={{ width: `${progressFraction(milestone) * 100}%` }} />
          </span>
          <span className={styles.progressText}>{progress}</span>
        </p>
      )}
      {tierLine && <p className={styles.meta}>{tierLine}</p>}
    </>
  );
}
