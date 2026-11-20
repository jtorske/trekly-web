"use client";

import Link from "next/link";
import { X } from "lucide-react";
import Avatar from "@/components/Avatar";
import FollowButton from "@/components/FollowButton";
import { hikerName, suggestionReason, type HikerResult } from "@/lib/hikerSearch";
import { publicProfilePath } from "@/lib/profilesApi";
import styles from "./activity.module.css";

/**
 * A slim card near the top of the feed for someone who follows nobody yet:
 * three hikers to follow (people with trails or a province in common first,
 * then authors of the suggested posts), one line each with a Follow button.
 * Dismissing it is remembered on this device.
 */
export default function FollowPrompt({
  hikers,
  place,
  onDismiss,
}: {
  hikers: HikerResult[];
  /** The viewer's home province name, for "Also from Alberta". */
  place: string | null;
  onDismiss: () => void;
}) {
  return (
    <li className={styles.followPrompt} aria-labelledby="follow-prompt-title">
      <div className={styles.followPromptHead}>
        <h2 id="follow-prompt-title" className={styles.followPromptTitle}>
          Follow hikers to see their hikes here
        </h2>
        <button type="button" className={styles.followPromptClose} onClick={onDismiss} aria-label="Dismiss">
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <ul className={styles.followPromptList}>
        {hikers.map((hiker) => {
          const name = hikerName(hiker);
          const why = hiker.common_trails || hiker.same_province ? suggestionReason(hiker, place) : null;
          return (
            <li key={hiker.username} className={styles.followPromptRow}>
              <Link href={publicProfilePath(hiker.username)} className={styles.followPromptWho}>
                <Avatar path={hiker.avatar_path} name={hiker.display_name ?? hiker.username} email={null} size={36} />
                <span className={styles.followPromptText}>
                  <span className={styles.followPromptName}>{name}</span>
                  <span className={styles.followPromptMeta}>{why ?? `@${hiker.username}`}</span>
                </span>
              </Link>
              <FollowButton username={hiker.username} name={name} state={hiker.follow} isPrivate={hiker.is_private} size="sm" />
            </li>
          );
        })}
      </ul>
    </li>
  );
}
