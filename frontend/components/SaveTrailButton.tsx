"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { nextQuery } from "@/lib/authLogic";
import styles from "./SaveTrailButton.module.css";

/**
 * Bookmark toggle. Signed-out visitors are sent to sign in and returned to
 * `returnTo` with `save=<trailId>` so the save completes after login.
 */
export default function SaveTrailButton({
  trailId,
  trailName,
  saved,
  pending,
  onToggle,
  returnTo,
  compact = false,
}: {
  trailId: string;
  trailName: string;
  saved: boolean;
  pending: boolean;
  onToggle: (trailId: string, makeSaved: boolean) => Promise<void>;
  returnTo: string;
  compact?: boolean;
}) {
  const { status } = useAuth();
  const router = useRouter();
  const click = async () => {
    if (status !== "signedIn") {
      const separator = returnTo.includes("?") ? "&" : "?";
      router.push(`/login${nextQuery(`${returnTo}${separator}save=${trailId}`)}`);
      return;
    }
    // Success and failure both toast (see useSavedTrails).
    await onToggle(trailId, !saved).catch(() => undefined);
  };

  return (
    <span className={styles.wrap}>
      <button
        type="button"
        className={`${styles.button} ${saved ? styles.saved : ""} ${compact ? styles.compact : ""}`}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          void click();
        }}
        aria-pressed={saved}
        aria-label={saved ? `Remove ${trailName} from saved trails` : `Save ${trailName}`}
        disabled={pending || status === "loading"}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className={styles.icon}>
          <path d="M6 3h12v18l-6-4.5L6 21Z" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        </svg>
        {!compact && <span>{saved ? "Saved" : "Save trail"}</span>}
      </button>
    </span>
  );
}
