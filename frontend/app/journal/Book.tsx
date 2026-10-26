"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { spreadCount, spreadOfPage, spreadPages } from "@/lib/journal";
import styles from "./journal.module.css";

const DESKTOP_QUERY = "(min-width: 860px)";
const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";
const SWIPE_PX = 40;

function useMedia(query: string, serverValue: boolean) {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => serverValue,
  );
}

type Flip = { to: number; dir: 1 | -1 };

/**
 * A book of `count` pages. Desktop shows two-page spreads (the cover alone
 * on the right) and turns a leaf with a CSS 3D rotation; phones show one
 * page at a time and turn on a swipe. Arrow keys and the buttons below flip
 * either way. With reduced motion, pages cross-fade instead.
 *
 * `render(page, active)` draws a page; `active` is false for the faces of a
 * leaf mid-turn, so pages can hold off one-time effects until they settle.
 * `request` jumps to a page (e.g. from the contents) when it changes.
 */
export default function Book({
  count,
  render,
  request,
  label,
}: {
  count: number;
  render: (page: number, active: boolean) => ReactNode;
  request: { page: number; seq: number } | null;
  label: string;
}) {
  const desktop = useMedia(DESKTOP_QUERY, true);
  const reduced = useMedia(REDUCED_QUERY, false);
  // The page shown on phones; on desktop, any page of the shown spread.
  const [at, setAt] = useState(0);
  const [flip, setFlip] = useState<Flip | null>(null);
  const [fadeKey, setFadeKey] = useState(0);
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const liveRef = useRef<HTMLParagraphElement>(null);

  const position = desktop ? spreadOfPage(at) : at;
  const positions = desktop ? spreadCount(count) : count;
  const pageOf = useCallback((pos: number) => (desktop ? Math.max(0, spreadPages(pos)[0]) : pos), [desktop]);

  const go = useCallback(
    (target: number) => {
      if (flip) return;
      const pos = desktop ? spreadOfPage(target) : target;
      if (target < 0 || target >= count || pos === position) return;
      if (reduced) {
        setAt(target);
        setFadeKey((k) => k + 1);
        return;
      }
      setFlip({ to: target, dir: pos > position ? 1 : -1 });
    },
    [flip, desktop, count, position, reduced],
  );

  const step = useCallback((dir: 1 | -1) => go(pageOf(position + dir)), [go, pageOf, position]);

  const finish = () => {
    if (!flip) return;
    setAt(flip.to);
    setFlip(null);
  };

  // Jump requests from the contents page.
  const lastRequest = useRef(0);
  useEffect(() => {
    if (!request || request.seq === lastRequest.current) return;
    lastRequest.current = request.seq;
    go(request.page);
  }, [request, go]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable], dialog")) return;
      if (event.key === "ArrowRight") step(1);
      else if (event.key === "ArrowLeft") step(-1);
      else return;
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  // Announce where we are once a turn settles.
  const where = desktop
    ? position === 0
      ? "Cover"
      : `Pages ${spreadPages(position)[0]}–${Math.min(spreadPages(position)[1], count - 1)} of ${count - 1}`
    : at === 0
      ? "Cover"
      : `Page ${at} of ${count - 1}`;
  useEffect(() => {
    if (!flip && liveRef.current) liveRef.current.textContent = where;
  }, [flip, where]);

  const page = (index: number, active: boolean, extra = "") =>
    index >= 0 && index < count ? (
      <div className={`${styles.sheet} ${extra}`} key={`${index}-${active}`}>
        {render(index, active)}
      </div>
    ) : null;

  let slots: ReactNode;
  if (desktop) {
    const [left, right] = spreadPages(position);
    const target = flip ? spreadPages(spreadOfPage(flip.to)) : null;
    const showLeft = flip?.dir === -1 && target ? target[0] : left;
    const showRight = flip?.dir === 1 && target ? target[1] : right;
    slots = (
      <>
        <div className={`${styles.slot} ${styles.leftSlot}`}>{page(showLeft, !flip, styles.leftPage)}</div>
        <div className={`${styles.slot} ${styles.rightSlot}`}>{page(showRight, !flip, styles.rightPage)}</div>
        {flip && target && (
          <div
            className={`${styles.leaf} ${flip.dir === 1 ? styles.turnForward : styles.turnBack}`}
            onAnimationEnd={(event) => event.target === event.currentTarget && finish()}
            aria-hidden="true"
          >
            <div className={`${styles.face} ${styles.front}`}>{page(flip.dir === 1 ? right : target[1], false, styles.rightPage)}</div>
            <div className={`${styles.face} ${styles.back}`}>{page(flip.dir === 1 ? target[0] : left, false, styles.leftPage)}</div>
          </div>
        )}
      </>
    );
  } else {
    const under = flip ? (flip.dir === 1 ? flip.to : at) : at;
    slots = (
      <>
        <div className={`${styles.slot} ${styles.singleSlot}`}>{page(under, !flip, styles.rightPage)}</div>
        {flip && (
          <div
            className={`${styles.leaf} ${styles.singleLeaf} ${flip.dir === 1 ? styles.turnForwardSingle : styles.turnBackSingle}`}
            onAnimationEnd={(event) => event.target === event.currentTarget && finish()}
            aria-hidden="true"
          >
            <div className={`${styles.face} ${styles.front}`}>{page(flip.dir === 1 ? at : flip.to, false, styles.rightPage)}</div>
            <div className={`${styles.face} ${styles.back}`}>
              <div className={`${styles.sheet} ${styles.leftPage}`} />
            </div>
          </div>
        )}
      </>
    );
  }

  const closed = desktop && (flip ? spreadOfPage(flip.to) : position) === 0;

  return (
    <section className={styles.bookArea} aria-roledescription="book" aria-label={label}>
      <div
        className={`${styles.stage} ${desktop ? styles.spread : styles.single} ${closed ? styles.closed : ""}`}
        onPointerDown={(event) => {
          if (event.pointerType !== "mouse") pointer.current = { x: event.clientX, y: event.clientY };
        }}
        onPointerUp={(event) => {
          const start = pointer.current;
          pointer.current = null;
          if (!start) return;
          const dx = event.clientX - start.x;
          const dy = event.clientY - start.y;
          if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy) * 1.5) step(dx < 0 ? 1 : -1);
        }}
        onPointerCancel={() => {
          pointer.current = null;
        }}
      >
        <div className={styles.pages} key={reduced ? fadeKey : undefined} data-fade={reduced || undefined}>
          {slots}
        </div>
      </div>

      <div className={styles.controls}>
        <button type="button" className={styles.flipButton} onClick={() => step(-1)} disabled={position === 0 || Boolean(flip)} aria-label="Previous page">
          <span aria-hidden="true">←</span>
        </button>
        <p className={styles.where} aria-hidden="true">
          {where}
        </p>
        <button
          type="button"
          className={styles.flipButton}
          onClick={() => step(1)}
          disabled={position >= positions - 1 || Boolean(flip)}
          aria-label="Next page"
        >
          <span aria-hidden="true">→</span>
        </button>
      </div>
      <p className={styles.hint}>{desktop ? "Use ← → to turn the pages." : "Swipe to turn the pages."}</p>
      <p ref={liveRef} className={styles.srOnly} aria-live="polite" />
    </section>
  );
}
