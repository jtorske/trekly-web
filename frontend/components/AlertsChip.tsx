import { BellRing } from "lucide-react";
import styles from "./AlertsChip.module.css";

/**
 * "Alerts available": shown on trail cards and trail pages when at least one
 * of the trail's campgrounds can be watched (has_watchable_campgrounds,
 * worked out on the server).
 */
export default function AlertsChip({ size = "sm" }: { size?: "sm" | "md" }) {
  return (
    <span
      className={styles.chip}
      data-size={size}
      title="Get an email when a campground on this trail opens up"
    >
      <BellRing aria-hidden="true" className={styles.icon} strokeWidth={2.2} />
      Alerts available
    </span>
  );
}
