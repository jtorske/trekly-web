"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import styles from "./journal.module.css";

const DESKTOP_QUERY = "(min-width: 860px)";
const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

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

/** Which page of a section to draw: a side of a desktop spread, or a phone's one page. */
export type View = "left" | "right" | "single";

type Flip = { to: number; dir: 1 | -1 };

/**
 * An open book of `count` sections. Desktop shows each section as a
 * two-page spread and turns a leaf with a CSS 3D rotation; phones show one
 * page. The book has no controls of its own: it turns to `at` whenever that
 * changes (the contents links move it), cross-fading with reduced motion.
 *
 * `render(section, view, active)` draws a page; `active` is false for the
 * faces of a leaf mid-turn, so pages can hold off one-time effects until
 * they settle. `name(section)` is announced once a turn settles.
 */
export default function Book({
  count,
  at,
  render,
  name,
  label,
}: {
  count: number;
  at: number;
  render: (section: number, view: View, active: boolean) => ReactNode;
  name: (section: number) => string;
  label: string;
}) {
  const desktop = useMedia(DESKTOP_QUERY, true);
  const reduced = useMedia(REDUCED_QUERY, false);
  const target = Math.min(Math.max(at, 0), count - 1);
  const [shown, setShown] = useState(target);
  const [flip, setFlip] = useState<Flip | null>(null);
  const [fadeKey, setFadeKey] = useState(0);
  const stageRef = useRef<HTMLDivElement>(null);
  const liveRef = useRef<HTMLParagraphElement>(null);
  const settled = useRef(shown);

  // Start the next turn as soon as the book is still and somewhere else is asked for.
  if (!flip && target !== shown) {
    if (reduced) {
      setShown(target);
      setFadeKey((k) => k + 1);
    } else {
      setFlip({ to: target, dir: target > shown ? 1 : -1 });
    }
  }

  const finish = () => {
    if (!flip) return;
    setShown(flip.to);
    setFlip(null);
  };

  // Once a turn settles, say where we are and move focus onto the new page.
  useEffect(() => {
    if (flip || settled.current === shown) return;
    settled.current = shown;
    if (liveRef.current) liveRef.current.textContent = name(shown);
    stageRef.current?.querySelector<HTMLElement>("[data-page-title]")?.focus({ preventScroll: true });
  }, [flip, shown, name]);

  const page = (index: number, view: View, active: boolean, extra: string) => (
    <div className={`${styles.sheet} ${extra}`} key={`${index}-${view}-${active}`}>
      {render(index, view, active)}
    </div>
  );

  let slots: ReactNode;
  if (desktop) {
    const left = flip?.dir === -1 ? flip.to : shown;
    const right = flip?.dir === 1 ? flip.to : shown;
    slots = (
      <>
        <div className={`${styles.slot} ${styles.leftSlot}`}>{page(left, "left", !flip, styles.leftPage)}</div>
        <div className={`${styles.slot} ${styles.rightSlot}`}>{page(right, "right", !flip, styles.rightPage)}</div>
        {flip && (
          <div
            className={`${styles.leaf} ${flip.dir === 1 ? styles.turnForward : styles.turnBack}`}
            onAnimationEnd={(event) => event.target === event.currentTarget && finish()}
            aria-hidden="true"
            inert
          >
            <div className={`${styles.face} ${styles.front}`}>{page(flip.dir === 1 ? shown : flip.to, "right", false, styles.rightPage)}</div>
            <div className={`${styles.face} ${styles.back}`}>{page(flip.dir === 1 ? flip.to : shown, "left", false, styles.leftPage)}</div>
          </div>
        )}
      </>
    );
  } else {
    const under = flip ? (flip.dir === 1 ? flip.to : shown) : shown;
    slots = (
      <>
        <div className={`${styles.slot} ${styles.singleSlot}`}>{page(under, "single", !flip, styles.rightPage)}</div>
        {flip && (
          <div
            className={`${styles.leaf} ${styles.singleLeaf} ${flip.dir === 1 ? styles.turnForwardSingle : styles.turnBackSingle}`}
            onAnimationEnd={(event) => event.target === event.currentTarget && finish()}
            aria-hidden="true"
            inert
          >
            <div className={`${styles.face} ${styles.front}`}>{page(flip.dir === 1 ? shown : flip.to, "single", false, styles.rightPage)}</div>
            <div className={`${styles.face} ${styles.back}`}>
              <div className={`${styles.sheet} ${styles.leftPage}`} />
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <section className={styles.bookArea} aria-roledescription="book" aria-label={label}>
      <div ref={stageRef} className={`${styles.stage} ${desktop ? styles.spread : styles.single}`}>
        <div className={styles.pages} key={reduced ? fadeKey : undefined} data-fade={reduced || undefined}>
          {slots}
        </div>
      </div>
      <p ref={liveRef} className={styles.srOnly} aria-live="polite" />
    </section>
  );
}
