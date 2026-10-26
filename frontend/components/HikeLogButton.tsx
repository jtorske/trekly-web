"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";
import HikeLogDialog from "./HikeLogDialog";
import { nextQuery } from "@/lib/authLogic";
import type { HikeLog, HikeLogInput } from "@/lib/hikeLogsApi";
import styles from "./SaveTrailButton.module.css";

const formatHiked = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

/**
 * "Mark as hiked" on a trail page. Once logged it shows the date and opens
 * the same dialog to edit or remove the entry. Guests are sent to sign in.
 * Retired trails take no new entries, so the button only appears there for
 * an existing one.
 */
export default function HikeLogButton({
  trailId,
  trailName,
  retired,
  entry,
  loading,
  onSave,
  onRemove,
  returnTo,
}: {
  trailId: string;
  trailName: string;
  retired: boolean;
  entry: HikeLog | null;
  loading: boolean;
  onSave: (trailId: string, input: HikeLogInput) => Promise<unknown>;
  onRemove: (trailId: string) => Promise<void>;
  returnTo: string;
}) {
  const { status } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  if (retired && !entry) return null;

  return (
    <>
      <button
        type="button"
        className={`${styles.button} ${entry ? styles.saved : ""}`}
        disabled={status === "loading" || (status === "signedIn" && loading)}
        onClick={() => {
          if (status !== "signedIn") {
            router.push(`/login${nextQuery(returnTo)}`);
            return;
          }
          setOpen(true);
        }}
        aria-label={entry ? `Hiked ${formatHiked(entry.hiked_on)}. Edit this journal entry` : `Mark ${trailName} as hiked`}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className={styles.icon}>
          {entry ? (
            <path d="m5 12.5 4.2 4.2L19 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          ) : (
            <path d="M3 20h18L14.5 8.5 11 14l-2.5-3.5Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          )}
        </svg>
        <span>{entry ? `Hiked ${formatHiked(entry.hiked_on)}` : "Mark as hiked"}</span>
      </button>
      {open && (
        <HikeLogDialog
          trailName={trailName}
          entry={entry}
          onSave={(input) => onSave(trailId, input)}
          onRemove={() => onRemove(trailId)}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
