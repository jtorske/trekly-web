"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { formatHikeDate } from "@/lib/publicProfile";
import { earnedSummary, earnedWhen, milestoneDetail, progressFraction, progressLabel, TIER_NAMES, type Milestone, type Tier } from "@/lib/milestones";
import type { UnitSystem } from "@/lib/units";
import styles from "./MilestoneCard.module.css";

const GAP = 8;
const MARGIN = 8;
// Long enough to cross the gap from the medal to its card with a mouse.
const HOVER_GRACE_MS = 150;
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * Someone's earned badge (an Activity post, a profile's featured badges): the
 * card shows the badge and whose it is, and words the requirement in the
 * present tense, since it's about what it takes rather than what they did.
 */
export interface BadgeView {
  /** The badge art, drawn at the top of the card. */
  art: ReactNode;
  /** "Earned by Ana", or just "Earned" for the viewer's own. */
  status: string;
  /** "Earned Oct 30", or null when their dates are hidden. */
  when: string | null;
}

/**
 * A medal that explains itself. Hovering it (with a mouse), focusing it from
 * the keyboard, or tapping it shows a card: for an earned milestone, a check,
 * how it was earned, the day and the tier; for the rest, what it takes and
 * how far along it is. A tap or click pins the card until the next tap,
 * Escape, or a tap elsewhere.
 *
 * With `badge` it describes someone's earned badge instead (see BadgeView),
 * and `footer` adds a last row that may hold a link: Tab from the medal moves
 * into the card, and Tab off its end carries on after the medal.
 *
 * The card is portalled to the body with fixed positioning: the book's pages
 * clip their contents and are transformed while they turn.
 */
export default function MilestoneCard({
  milestone,
  units,
  tierPoints,
  badge,
  footer,
  label,
  variant = "medal",
  keyboard = true,
  className = "",
  children,
}: {
  milestone: Milestone;
  units: UnitSystem;
  tierPoints?: Record<Tier, number>;
  badge?: BadgeView;
  footer?: ReactNode;
  /** The trigger's accessible name; "Details for <title>" by default. */
  label?: string;
  /** "text" for a name in a sentence rather than the medal art. */
  variant?: "medal" | "text";
  /** false for a second way into the same card (a post's badge beside its name): pointers only. */
  keyboard?: boolean;
  className?: string;
  /** The medal art, or the name for variant "text". */
  children: ReactNode;
}) {
  const hidden = milestone.secret && !milestone.earned;
  const name = hidden ? "the secret milestone" : milestone.title;
  return (
    <DetailCard
      label={label ?? `Details for ${name}`}
      dialogLabel={`${hidden ? "Secret milestone" : milestone.title} details`}
      earned={milestone.earned}
      variant={variant}
      keyboard={keyboard}
      className={className}
      footer={footer}
      body={
        badge ? (
          <BadgeBody milestone={milestone} units={units} badge={badge} />
        ) : (
          <CardBody milestone={milestone} units={units} tierPoints={tierPoints} />
        )
      }
    >
      {children}
    </DetailCard>
  );
}

/**
 * The hover, focus and tap card behind MilestoneCard, for any badge: a trail
 * stamp, the home province badge. `body` is the card's content (BadgeCardBody
 * for a badge); `footer` adds a last row that may hold a link, which makes the
 * card a small dialog that Tab moves into.
 *
 * It's portalled to the body with fixed positioning and kept inside the
 * window, so no scrolling area or card edge can clip it, on a phone too.
 */
export function DetailCard({
  label,
  dialogLabel,
  body,
  footer,
  earned = false,
  variant = "medal",
  keyboard = true,
  className = "",
  children,
}: {
  /** The trigger's accessible name. */
  label: string;
  /** The card's name when it holds a link. */
  dialogLabel?: string;
  body: ReactNode;
  footer?: ReactNode;
  /** Colours the status line green. */
  earned?: boolean;
  variant?: "medal" | "text";
  keyboard?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const hoverTimer = useRef<number | undefined>(undefined);
  // Set while focus is handed back to the medal, so that doesn't reopen it.
  const returning = useRef(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hovered || focused || pinned;

  const close = useCallback(() => {
    window.clearTimeout(hoverTimer.current);
    setHovered(false);
    setFocused(false);
    setPinned(false);
  }, []);

  const hoverIn = (event: ReactPointerEvent) => {
    if (event.pointerType !== "mouse") return;
    window.clearTimeout(hoverTimer.current);
    setHovered(true);
  };
  const hoverOut = (event: ReactPointerEvent) => {
    if (event.pointerType !== "mouse") return;
    window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(() => setHovered(false), HOVER_GRACE_MS);
  };
  useEffect(() => () => window.clearTimeout(hoverTimer.current), []);

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

  const focusTrigger = useCallback(() => {
    returning.current = true;
    trigger.current?.focus();
    returning.current = false;
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Only this card closes; nothing else (a dialog, the book) hears it.
        event.stopPropagation();
        const inside = card.current?.contains(document.activeElement);
        close();
        if (inside) focusTrigger();
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !card.current?.contains(event.target as Node)) close();
    };
    window.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    // Content can arrive while it's open (the viewer's own standing loads late).
    const resized = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(place);
    if (card.current) resized?.observe(card.current);
    return () => {
      resized?.disconnect();
      window.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, close, place, focusTrigger]);

  const focusables = () => Array.from(card.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);

  /** Tab off the card's end: on to whatever follows the medal on the page. */
  const tabPastTrigger = () => {
    const all = Array.from(document.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => !card.current?.contains(el) && el.tabIndex >= 0 && el.getClientRects().length > 0,
    );
    const at = trigger.current ? all.indexOf(trigger.current) : -1;
    close();
    const next = at >= 0 ? all[at + 1] : undefined;
    if (next) next.focus();
    else focusTrigger();
  };

  const interactive = Boolean(footer);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={`${variant === "text" ? styles.textTrigger : styles.trigger} ${className}`}
        aria-label={label}
        tabIndex={keyboard ? undefined : -1}
        aria-hidden={keyboard ? undefined : true}
        aria-expanded={open}
        aria-describedby={open && !interactive ? id : undefined}
        aria-controls={open && interactive ? id : undefined}
        onPointerEnter={hoverIn}
        onPointerLeave={hoverOut}
        onFocus={(event) => {
          if (!returning.current) setFocused(event.currentTarget.matches(":focus-visible"));
        }}
        onBlur={(event) => {
          if (!card.current?.contains(event.relatedTarget as Node | null)) close();
        }}
        onKeyDown={(event) => {
          if (event.key !== "Tab" || event.shiftKey || !open) return;
          const first = focusables()[0];
          if (first) {
            event.preventDefault();
            first.focus();
          }
        }}
        onClick={() => (pinned ? close() : setPinned(true))}
      >
        {children}
      </button>
      {open &&
        createPortal(
          <div
            ref={card}
            id={id}
            role={interactive ? "dialog" : "tooltip"}
            aria-label={interactive ? (dialogLabel ?? label) : undefined}
            className={styles.card}
            data-earned={earned || undefined}
            style={{ left: 0, top: 0, visibility: "hidden" }}
            onPointerEnter={hoverIn}
            onPointerLeave={hoverOut}
            onBlur={(event) => {
              const to = event.relatedTarget as Node | null;
              if (!card.current?.contains(to) && !trigger.current?.contains(to)) close();
            }}
            onKeyDown={(event) => {
              if (event.key !== "Tab") return;
              const items = focusables();
              if (event.shiftKey && document.activeElement === items[0]) {
                event.preventDefault();
                focusTrigger();
              } else if (!event.shiftKey && document.activeElement === items[items.length - 1]) {
                event.preventDefault();
                tabPastTrigger();
              }
            }}
          >
            {body}
            {footer && <div className={styles.footer}>{footer}</div>}
          </div>,
          document.body,
        )}
    </>
  );
}

function TierLine({ milestone, tierPoints }: { milestone: Milestone; tierPoints?: Record<Tier, number> }) {
  if (!milestone.tier) return null;
  const points = tierPoints ? tierPoints[milestone.tier] : null;
  return (
    <span className={styles.tier} data-tier={milestone.tier}>
      {TIER_NAMES[milestone.tier]} tier{points != null && <> · +{points} pts</>}
    </span>
  );
}

function Check() {
  return (
    <svg viewBox="0 0 24 24" className={styles.check} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="m7.5 12.5 3 3 6-7" />
    </svg>
  );
}

/**
 * A badge's card: its art beside a status line (with a check when `earned`)
 * and its name, then whatever lines follow.
 */
export function BadgeCardBody({
  art,
  status,
  title,
  sub,
  earned = false,
  children,
}: {
  art: ReactNode;
  status?: string;
  title: string;
  /** A muted line under the name, e.g. a trail's park. */
  sub?: string | null;
  earned?: boolean;
  children?: ReactNode;
}) {
  return (
    <>
      <div className={styles.badgeHead}>
        <span className={styles.badgeArt} aria-hidden="true">
          {art}
        </span>
        <span className={styles.badgeHeadText}>
          {status && (
            <span className={styles.status}>
              {earned && <Check />}
              {status}
            </span>
          )}
          <span className={styles.title}>{title}</span>
          {sub && <span className={styles.sub}>{sub}</span>}
        </span>
      </div>
      {children}
    </>
  );
}

/** A plain line under a BadgeCardBody's head, e.g. a trail's park. */
export function CardLine({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <p className={muted ? styles.meta : styles.how}>{children}</p>;
}

function BadgeBody({ milestone, units, badge }: { milestone: Milestone; units: UnitSystem; badge: BadgeView }) {
  const detail = milestoneDetail(milestone, units);
  return (
    <BadgeCardBody art={badge.art} status={badge.status} title={milestone.title} earned>
      {detail && <p className={styles.how}>{detail}</p>}
      <p className={styles.meta}>
        {badge.when && <span>{badge.when}</span>}
        <TierLine milestone={milestone} />
      </p>
    </BadgeCardBody>
  );
}

function CardBody({ milestone, units, tierPoints }: { milestone: Milestone; units: UnitSystem; tierPoints?: Record<Tier, number> }) {
  const tierLine = <TierLine milestone={milestone} tierPoints={tierPoints} />;

  if (milestone.earned) {
    const when = earnedWhen(milestone, formatHikeDate);
    return (
      <>
        <p className={styles.status}>
          <Check />
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
      {milestone.tier && <p className={styles.meta}>{tierLine}</p>}
    </>
  );
}
