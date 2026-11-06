import styles from "./VerifiedCheck.module.css";

export const VERIFIED_LABEL = "Verified with a GPS track";

/**
 * The small check beside a hike that was matched against a GPS track. The
 * tooltip is the native title (hover) plus a visually hidden label, so touch
 * and screen-reader users get the same words.
 */
export default function VerifiedCheck({ className, size = 14 }: { className?: string; size?: number }) {
  return (
    <span className={`${styles.check} ${className ?? ""}`} title={VERIFIED_LABEL} role="img" aria-label={VERIFIED_LABEL}>
      <svg viewBox="0 0 16 16" width={size} height={size} aria-hidden="true">
        <path
          d="M8 .8 9.9 2.2l2.3-.1.7 2.2 1.9 1.4-.8 2.3.8 2.2-1.9 1.4-.7 2.2-2.3-.1L8 15.2l-1.9-1.4-2.3.1-.7-2.2L1.2 10.3 2 8 1.2 5.7l1.9-1.4.7-2.2 2.3.1Z"
          fill="currentColor"
        />
        <path d="m5.2 8.2 1.9 1.9 3.8-4" fill="none" stroke="var(--verified-tick, #fff)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}
