"use client";

import { useEffect } from "react";
import { dismissCelebration, useRank } from "@/lib/useRank";
import RankEmblem from "./RankEmblem";
import styles from "./RankCelebration.module.css";

const SHOW_MS = 3600;

/**
 * Plays once when logging a hike crosses into a new rank: the emblem
 * stamps down like a passport stamp (a plain fade with reduced motion).
 * Mounted once in the layout; lib/useRank decides when, and never on a
 * page load.
 */
export default function RankCelebration() {
  const { celebrating } = useRank();

  useEffect(() => {
    if (!celebrating) return;
    const timer = window.setTimeout(dismissCelebration, SHOW_MS);
    return () => window.clearTimeout(timer);
  }, [celebrating]);

  return (
    <div className={styles.region} role="status" aria-live="polite">
      {celebrating && (
        <button type="button" key={celebrating.level} className={styles.card} onClick={dismissCelebration}>
          <RankEmblem level={celebrating.level} className={styles.emblem} />
          <span className={styles.text}>
            <span className={styles.eyebrow}>Rank up</span>
            <span className={styles.title}>You&apos;re now a {celebrating.title}</span>
          </span>
          <span className={styles.srHint}>Dismiss</span>
        </button>
      )}
    </div>
  );
}
