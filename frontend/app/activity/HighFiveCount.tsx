"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AccountBadge from "@/components/AccountBadge";
import Avatar from "@/components/Avatar";
import Dialog from "@/components/Dialog";
import FollowButton from "@/components/FollowButton";
import ui from "@/components/ui.module.css";
import { highFivesLabel, type ActivityPost, type HighFiver, type HighFivers } from "@/lib/activity";
import { getHighFivers } from "@/lib/activityApi";
import { publicProfilePath } from "@/lib/profilesApi";
import { displayName } from "@/lib/publicProfile";
import styles from "./activity.module.css";

/**
 * "3 high fives" in a post's footer; clicking it lists who: avatar, name,
 * @username and a Follow button for each hiker the reader may see (public
 * profiles, ones they follow), and "and 2 others" for the rest (private
 * profiles, blocked hikers). The post's author always sees their count,
 * "No high fives yet" included; others see nothing until there's one.
 */
export default function HighFiveCount({
  post,
  signedIn,
  viewer,
}: {
  post: Pick<ActivityPost, "id" | "high_fives" | "mine">;
  signedIn: boolean;
  viewer: string | null;
}) {
  const [open, setOpen] = useState(false);
  const count = post.high_fives;

  if (count === 0) {
    return post.mine ? <span className={styles.fiveNone}>{highFivesLabel(0)}</span> : null;
  }
  return (
    <>
      <button
        type="button"
        className={styles.fiveCount}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        {highFivesLabel(count)}
        <span className={ui.srOnly}>: show who</span>
      </button>
      {open && <HighFiversDialog postId={post.id} count={count} signedIn={signedIn} viewer={viewer} onClose={() => setOpen(false)} />}
    </>
  );
}

function HighFiversDialog({
  postId,
  count,
  signedIn,
  viewer,
  onClose,
}: {
  postId: string;
  count: number;
  signedIn: boolean;
  viewer: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<HighFivers | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getHighFivers(postId, signedIn, controller.signal)
      .then(setData)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [postId, signedIn, count]);

  const setFollow = (hiker: HighFiver, state: HighFiver["follow"]) =>
    setData((current) =>
      current && {
        ...current,
        hikers: current.hikers.map((h) => (h.username === hiker.username ? { ...h, follow: state } : h)),
      },
    );

  return (
    <Dialog title="High fives" subtitle={highFivesLabel(data?.high_fives ?? count)} size="sm" onClose={onClose}>
      {failed ? (
        <p className={ui.error}>Couldn&apos;t load who high-fived. Try again in a moment.</p>
      ) : !data ? (
        <p className={ui.hint} role="status">
          Loading…
        </p>
      ) : (
        <>
          <ul className={styles.fiverList}>
            {data.hikers.map((hiker) => {
              const name = displayName(hiker);
              const you = hiker.username === viewer;
              return (
                <li key={hiker.username} className={styles.fiverRow}>
                  <Link href={publicProfilePath(hiker.username)} className={styles.fiverWho} onClick={onClose}>
                    <Avatar path={hiker.avatar_path} name={hiker.display_name ?? hiker.username} email={null} size={40} />
                    <span className={styles.fiverText}>
                      <span className={styles.fiverName}>
                        {you ? "You" : name}
                        <AccountBadge label={hiker.label} compact />
                      </span>
                      <span className={styles.fiverHandle}>@{hiker.username}</span>
                    </span>
                  </Link>
                  {hiker.follow !== null && !you && (
                    <FollowButton
                      username={hiker.username}
                      name={name}
                      state={hiker.follow}
                      isPrivate={hiker.is_private}
                      size="sm"
                      onChange={(state) => setFollow(hiker, state)}
                    />
                  )}
                </li>
              );
            })}
          </ul>
          {data.others > 0 && (
            <p className={ui.hint}>
              {data.hikers.length > 0 ? "and " : ""}
              {data.others === 1 ? "1 other hiker" : `${data.others} other hikers`}
              {data.hikers.length === 0 ? " high-fived this" : ""}
            </p>
          )}
        </>
      )}
    </Dialog>
  );
}
