import { milestoneIcon } from "@/lib/badge";
import type { Tier } from "@/lib/milestones";
import styles from "./MilestoneBadge.module.css";

/**
 * A milestone medal: a dark disc with a cream line icon, ringed in its
 * tier's colour (bronze, silver or gold) once earned. Not yet earned, it's a
 * dashed outline with a faint icon and, given `progress`, an arc of how far
 * along it is. `stamp` presses it in like an ink stamp once (a fade with
 * reduced motion), then calls onStamped.
 *
 * With a `title` it's an image named for screen readers; without one it's
 * decoration beside text that already says it.
 */
export default function MilestoneBadge({
  icon,
  tier,
  earned = true,
  progress = 0,
  title,
  stamp = false,
  onStamped,
  className = "",
}: {
  icon: string;
  tier: Tier | null;
  earned?: boolean;
  /** 0–1; only drawn while not earned. */
  progress?: number;
  title?: string;
  stamp?: boolean;
  onStamped?: () => void;
  className?: string;
}) {
  const r = 46;
  const circumference = 2 * Math.PI * r;
  const label = title
    ? { role: "img", "aria-label": `${title}, ${tier ? `${tier} ` : ""}milestone badge` }
    : { "aria-hidden": true as const };
  return (
    <svg
      viewBox="0 0 120 120"
      {...label}
      className={`${styles.badge} ${earned ? styles.earned : ""} ${stamp ? styles.stamp : ""} ${className}`}
      data-tier={tier ?? undefined}
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget) onStamped?.();
      }}
    >
      <circle cx="60" cy="60" r="54" className={styles.base} />
      {earned && <circle cx="60" cy="60" r="45" className={styles.inner} />}
      {!earned && progress > 0 && (
        <circle
          cx="60"
          cy="60"
          r={r}
          className={styles.progress}
          strokeDasharray={`${circumference * Math.min(progress, 1)} ${circumference}`}
          transform="rotate(-90 60 60)"
        />
      )}
      <path d={milestoneIcon(icon)} className={styles.icon} />
    </svg>
  );
}
