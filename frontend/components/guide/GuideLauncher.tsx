"use client";

import { useState } from "react";
import GuidePlanner, { GuideAvatar } from "./GuidePlanner";
import styles from "./GuidePlanner.module.css";

/** "Plan with Trekly Guide": opens the planner. On Explore and at the end of /welcome. */
export default function GuideLauncher({
  hint = "Answer a few quick questions and get trails picked for you.",
  className,
}: {
  hint?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={`${styles.launcher} ${className ?? ""}`}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <GuideAvatar />
        <span className={styles.launcherText}>
          <span className={styles.launcherTitle}>Plan with Trekly Guide</span>
          <span className={styles.launcherHint}>{hint}</span>
        </span>
        <span className={styles.launcherArrow} aria-hidden="true">
          →
        </span>
      </button>
      {open && <GuidePlanner onClose={() => setOpen(false)} />}
    </>
  );
}
