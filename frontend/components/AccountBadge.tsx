import { BadgeCheck, FlaskConical } from "lucide-react";
import { ACCOUNT_BADGE_HINT, ACCOUNT_BADGE_TEXT, type AccountLabel } from "@/lib/accountLabels";
import styles from "./AccountBadge.module.css";

/**
 * "Trekly team" beside the official account's name, "Demo account" beside
 * a demo hiker's. Renders nothing for everyone else. The words are always
 * visible (not an icon alone), so they read the same on touch screens and
 * to screen readers; `compact` only makes it smaller.
 */
export default function AccountBadge({
  label,
  compact = false,
  className,
}: {
  label: AccountLabel | null | undefined;
  compact?: boolean;
  className?: string;
}) {
  if (label !== "official" && label !== "demo") return null;
  const Icon = label === "official" ? BadgeCheck : FlaskConical;
  return (
    <span
      className={`${styles.badge} ${styles[label]} ${compact ? styles.compact : ""} ${className ?? ""}`}
      title={ACCOUNT_BADGE_HINT[label]}
      data-account-label={label}
    >
      <Icon size={compact ? 12 : 13} aria-hidden="true" />
      {ACCOUNT_BADGE_TEXT[label]}
    </span>
  );
}
