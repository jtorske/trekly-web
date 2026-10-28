import { MILESTONE_ICONS } from "@/lib/badge";
import type { Milestone } from "@/lib/journal";
import styles from "./MilestoneBadge.module.css";

/**
 * An earned milestone medal, drawn like the Trail Journal's (gold disc,
 * foil rim, cream line icon), for places outside the journal.
 */
export default function MilestoneBadge({
  id,
  title,
  className = "",
}: {
  id: Milestone["id"];
  title: string;
  className?: string;
}) {
  return (
    <svg viewBox="0 0 120 120" role="img" aria-label={`${title}, milestone badge`} className={`${styles.badge} ${className}`}>
      <circle cx="60" cy="60" r="54" className={styles.base} />
      <path d={MILESTONE_ICONS[id]} className={styles.icon} />
    </svg>
  );
}
