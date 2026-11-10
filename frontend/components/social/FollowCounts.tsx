"use client";

import { useState } from "react";
import { countLabel } from "@/lib/follows";
import FollowListDialog, { type FollowTab } from "./FollowListDialog";
import styles from "./FollowCounts.module.css";

/**
 * "12 followers · 4 following" on a profile card. They open the lists when
 * the viewer may see them; otherwise they're plain text (the owner hid the
 * lists, or the profile is private to this viewer).
 */
export default function FollowCounts({
  username,
  name,
  followers,
  following,
  open,
  owner,
  signedIn,
  requests = 0,
  onCountsChange,
}: {
  username: string;
  name: string;
  followers: number;
  following: number;
  /** The viewer may open the lists. */
  open: boolean;
  owner: boolean;
  signedIn: boolean;
  /** Your own private profile: requests waiting. */
  requests?: number;
  onCountsChange?: (change: { followers?: number; requests?: number }) => void;
}) {
  const [showing, setShowing] = useState<FollowTab | null>(null);

  const item = (tab: FollowTab, label: string) =>
    open ? (
      <button type="button" className={styles.count} onClick={() => setShowing(tab)}>
        {label}
      </button>
    ) : (
      <span className={styles.plain}>{label}</span>
    );

  return (
    <div className={styles.row}>
      {item("followers", countLabel(followers, "followers"))}
      <span aria-hidden="true" className={styles.dot}>
        ·
      </span>
      {item("following", countLabel(following, "following"))}
      {owner && requests > 0 && (
        <>
          <span aria-hidden="true" className={styles.dot}>
            ·
          </span>
          <button type="button" className={`${styles.count} ${styles.requests}`} onClick={() => setShowing("requests")}>
            {requests === 1 ? "1 request" : `${requests} requests`}
          </button>
        </>
      )}
      {showing && (
        <FollowListDialog
          username={username}
          name={name}
          initialTab={showing}
          owner={owner}
          signedIn={signedIn}
          requestCount={requests}
          onClose={() => setShowing(null)}
          onCountsChange={onCountsChange}
        />
      )}
    </div>
  );
}
