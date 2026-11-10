"use client";

import { useState } from "react";
import Link from "next/link";
import { Flag, Hand, Trash2 } from "lucide-react";
import Avatar from "@/components/Avatar";
import Dialog from "@/components/Dialog";
import HikePhoto from "@/components/HikePhoto";
import MilestoneBadge from "@/components/MilestoneBadge";
import MilestoneBadgeCard from "@/components/MilestoneBadgeCard";
import RankEmblem from "@/components/RankEmblem";
import ReportDialog from "@/components/ReportDialog";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import VerifiedCheck from "@/components/VerifiedCheck";
import { postAction, postHref, shortAgo, type ActivityPost } from "@/lib/activity";

/** The screen-reader name for a compact post's badge link. */
const badgeLabel = (post: ActivityPost, name: string) => `${name} ${postAction(post)}`;
import { deleteActivityPost, setHighFive } from "@/lib/activityApi";
import { publicProfilePath } from "@/lib/profilesApi";
import { displayName, formatHikeDate } from "@/lib/publicProfile";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { toast } from "@/lib/toast";
import styles from "./activity.module.css";

/**
 * One post. A hike is a card with the trail (tap to open it), the date
 * (unless the hiker hides dates), and their note and photo. A milestone or
 * rank is one compact line with its badge (tap to open their profile).
 */
export default function PostCard({
  post,
  signedIn,
  signInHref,
  onChange,
}: {
  post: ActivityPost;
  signedIn: boolean;
  signInHref: string;
  /** null removes the post from the list. */
  onChange: (id: string, change: Partial<ActivityPost> | null) => void;
}) {
  const [reporting, setReporting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const name = displayName(post.author);
  const profileHref = publicProfilePath(post.author.username);

  const toggleHighFive = async () => {
    const on = !post.high_fived;
    // Optimistic; the server's count wins once it answers.
    onChange(post.id, { high_fived: on, high_fives: post.high_fives + (on ? 1 : -1) });
    try {
      onChange(post.id, await setHighFive(post.id, on));
    } catch (caught) {
      onChange(post.id, { high_fived: post.high_fived, high_fives: post.high_fives });
      toast.failure(on ? "send your high five" : "take back your high five", caught);
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await deleteActivityPost(post.id);
      onChange(post.id, null);
      toast.success("Post deleted. Your journal is unchanged.");
    } catch (caught) {
      toast.failure("delete the post", caught);
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const when = post.posted_at && (
    <time dateTime={post.posted_at} title={new Date(post.posted_at).toLocaleString("en-CA")}>
      {shortAgo(post.posted_at)}
    </time>
  );

  const actions = (
    <div className={styles.actions}>
      {signedIn ? (
        <button
          type="button"
          className={styles.highFive}
          aria-pressed={post.high_fived}
          onClick={() => void toggleHighFive()}
          aria-label={`High five${post.high_fived ? " (given)" : ""}, ${post.high_fives}`}
        >
          <Hand size={16} aria-hidden="true" />
          <span>High five</span>
          {post.high_fives > 0 && <span className={styles.count}>{post.high_fives}</span>}
        </button>
      ) : (
        <Link href={signInHref} className={styles.highFive} aria-label={`Sign in to high five, ${post.high_fives}`}>
          <Hand size={16} aria-hidden="true" />
          <span>High five</span>
          {post.high_fives > 0 && <span className={styles.count}>{post.high_fives}</span>}
        </Link>
      )}
      <span className={styles.spacer} />
      {post.mine ? (
        <button type="button" className={styles.iconAction} onClick={() => setConfirmDelete(true)}>
          <Trash2 size={14} aria-hidden="true" />
          Delete
        </button>
      ) : (
        signedIn && (
          <button type="button" className={styles.iconAction} onClick={() => setReporting(true)}>
            <Flag size={14} aria-hidden="true" />
            Report
          </button>
        )
      )}
    </div>
  );

  const dialogs = (
    <>
      {reporting && (
        <ReportDialog username={post.author.username} name={name} postId={post.id} onClose={() => setReporting(false)} />
      )}
      {confirmDelete && (
        <Dialog
          title="Delete this post?"
          subtitle="It leaves the Activity feed. Your hike, badges and journal stay as they are."
          onClose={() => setConfirmDelete(false)}
          busy={deleting}
          size="sm"
          footer={
            <>
              <button type="button" className={ui.ghost} onClick={() => setConfirmDelete(false)} disabled={deleting}>
                Keep it
              </button>
              <button type="button" className={ui.danger} onClick={() => void remove()} disabled={deleting}>
                {deleting ? "Deleting…" : "Delete post"}
              </button>
            </>
          }
        >
          {null}
        </Dialog>
      )}
    </>
  );

  if (post.kind !== "hike" || !post.hike) {
    return (
      <li className={`${styles.card} ${styles.compact}`}>
        <div className={styles.compactRow}>
          {post.milestone ? (
            // The badge and its name both open the milestone's card.
            <MilestoneBadgeCard badge={post.milestone} owner={name} mine={post.mine} keyboard={false} className={styles.compactBadge}>
              <MilestoneBadge icon={post.milestone.icon} tier={post.milestone.tier} className={styles.badge} />
            </MilestoneBadgeCard>
          ) : (
            <Link href={profileHref} className={styles.compactBadge} aria-hidden="true" tabIndex={-1} title={badgeLabel(post, name)}>
              <RankEmblem level={post.rank?.level ?? 1} className={styles.badge} />
            </Link>
          )}
          <p className={styles.compactText}>
            <Link href={postHref(post)} className={styles.name}>
              {name}
            </Link>{" "}
            {post.milestone ? (
              <>
                earned{" "}
                <MilestoneBadgeCard badge={post.milestone} owner={name} mine={post.mine} variant="text">
                  {post.milestone.title}
                </MilestoneBadgeCard>
              </>
            ) : (
              <>
                reached <strong>{post.rank?.title}</strong>
              </>
            )}
            {when && <span className={styles.meta}> · {when}</span>}
          </p>
        </div>
        {actions}
        {dialogs}
      </li>
    );
  }

  const { hike } = post;
  const trail = hike.trail;
  const place = trail.park_name ?? trail.region;
  return (
    <li className={styles.card}>
      <div className={styles.head}>
        <Link href={profileHref} className={styles.avatarLink} aria-label={`${name}'s profile`}>
          <Avatar path={post.author.avatar_path} name={post.author.display_name ?? post.author.username} email={null} size={40} />
        </Link>
        <div className={styles.who}>
          <span className={styles.nameRow}>
            <Link href={profileHref} className={styles.name}>
              {name}
            </Link>
            {hike.verified && <VerifiedCheck />}
          </span>
          <span className={styles.meta}>
            @{post.author.username}
            {when && <> · {when}</>}
          </span>
        </div>
      </div>

      <Link href={postHref(post)} className={styles.trail}>
        <span className={styles.trailThumb}>
          <TrailPhoto photo={trail.photo} name={trail.name} variant="thumb" />
        </span>
        <span className={styles.trailText}>
          <span className={styles.trailLabel}>Hiked</span>
          <span className={styles.trailName}>{trail.name}</span>
          <span className={styles.trailMeta}>
            {place}
            {" · "}
            {TERRAIN_LABELS[trail.terrain]}
            {hike.hiked_on && (
              <>
                {" · "}
                <time dateTime={hike.hiked_on}>{formatHikeDate(hike.hiked_on)}</time>
              </>
            )}
          </span>
        </span>
      </Link>

      {hike.note && <p className={styles.note}>{hike.note}</p>}
      {hike.photo_path && (
        <HikePhoto path={hike.photo_path} alt={`${name}'s photo from ${trail.name}`} className={styles.photo} />
      )}
      {actions}
      {dialogs}
    </li>
  );
}
