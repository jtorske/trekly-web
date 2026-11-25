import { Footprints, MountainSnow, Snowflake, TrainTrack, type LucideIcon } from "lucide-react";
import { WINTER_ACTIVITY_LABELS } from "@/lib/exploreFilters";
import type { WinterActivity } from "@/lib/trailsApi";
import styles from "./WinterBadge.module.css";

/** One icon per winter activity; always shown with its name (in text or for screen readers). */
export const WINTER_ACTIVITY_ICONS: Record<WinterActivity, LucideIcon> = {
  winter_hike: Footprints,
  snowshoe: MountainSnow,
  xc_ski: TrainTrack,
};

const ORDER: WinterActivity[] = ["winter_hike", "snowshoe", "xc_ski"];

/**
 * The small snowflake on a trail card in winter mode: the trail is listed
 * for winter use, with an icon per activity. Says nothing about safety.
 */
export default function WinterBadge({ activities }: { activities: WinterActivity[] }) {
  const listed = ORDER.filter((a) => activities.includes(a));
  if (listed.length === 0) return null;
  const names = listed.map((a) => WINTER_ACTIVITY_LABELS[a]).join(", ");
  return (
    <span className={styles.badge} title={`Winter: ${names}`}>
      <Snowflake className={styles.flake} aria-hidden="true" size={14} strokeWidth={2} />
      {listed.map((a) => {
        const Icon = WINTER_ACTIVITY_ICONS[a];
        return <Icon key={a} className={styles.icon} aria-hidden="true" size={14} strokeWidth={2} />;
      })}
      <span className={styles.srOnly}>Winter: {names}</span>
    </span>
  );
}
