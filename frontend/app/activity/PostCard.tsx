"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink, EyeOff, Flag, Hand, MessageCircle, MessageCircleOff, Sparkles, Trash2 } from "lucide-react";
import AccountBadge from "@/components/AccountBadge";
import Avatar from "@/components/Avatar";
import FollowButton from "@/components/FollowButton";
import HikePhoto from "@/components/HikePhoto";
import MoreMenu, { type MoreMenuItem } from "@/components/MoreMenu";
import MilestoneBadge from "@/components/MilestoneBadge";
import MilestoneBadgeCard from "@/components/MilestoneBadgeCard";
import RankEmblem from "@/components/RankEmblem";
import ReportDialog from "@/components/ReportDialog";
import ReviewNotice from "@/components/ReviewNotice";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import VerifiedCheck from "@/components/VerifiedCheck";
import { ONLY_YOU_LABEL, UNSHARED_LABEL, commentCount, deleteKey, earnedPhrases, formatSourceDate, postHref, shortAgo, type ActivityEarned, type ActivityPost } from "@/lib/activity";
import { deleteActivityPost, setCommentsOff, setHighFive } from "@/lib/activityApi";
import { publicProfilePath } from "@/lib/profilesApi";
import { displayName, formatHikeDate } from "@/lib/publicProfile";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { toast } from "@/lib/toast";
import { removeWithUndo } from "@/lib/undo";
import { sectionHref } from "@/app/settings/settingsSections";
import Comments from "./Comments";
import HighFiveCount from "./HighFiveCount";
import styles from "./activity.module.css";

/**
 * One post: who (avatar, name, @username, when), then what they did. A hike
 * says "Hiked <trail>", with whatever that hike earned folded into the same
 * line and shown as small badges, then their note, photo and the trail. A
 * milestone or rank that no shared hike explains is a post of its own.
 * Under it, the comments (Comments.tsx). Your own posts have a "⋯" menu
 * (turn comments off/on, Delete with Undo); others' offer Report.
 */
export default function PostCard({
  post,
  signedIn,
  signInHref,
  viewer,
  onChange,
  commentsOpen = false,
}: {
  post: ActivityPost;
  /** Every comment shown from the start (the post's own page). */
  commentsOpen?: boolean;
  signedIn: boolean;
  /** The signed-in viewer's username, so their own high five reads "You". */
  viewer: string | null;
  signInHref: string;
  /** null removes the post from the list. */
  onChange: (id: string, change: Partial<ActivityPost> | null) => void;
}) {
  const [reporting, setReporting] = useState(false);
  const [showAll, setShowAll] = useState(commentsOpen);
  const [focusKey, setFocusKey] = useState(0);
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

  const remove = () =>
    removeWithUndo({
      key: deleteKey(post.id),
      message: "Post deleted. Your hike and badges stay in your journal.",
      commit: () => deleteActivityPost(post.id),
      what: "delete the post",
      onCommitted: () => onChange(post.id, null),
    });

  const toggleComments = async () => {
    const off = !post.comments_off;
    onChange(post.id, { comments_off: off, can_comment: !off });
    try {
      const result = await setCommentsOff(post.id, off);
      onChange(post.id, { comments_off: result.comments_off, can_comment: !result.comments_off });
      toast.success(result.comments_off ? "Comments are off for this post." : "Comments are on again.");
    } catch (caught) {
      onChange(post.id, { comments_off: !off, can_comment: off });
      toast.failure(off ? "turn comments off" : "turn comments on", caught);
    }
  };

  const ownMenu: MoreMenuItem[] = post.mine
    ? [
        ...(post.only_you
          ? []
          : [{
              label: post.comments_off ? "Turn comments on" : "Turn comments off",
              icon: post.comments_off ? <MessageCircle size={15} aria-hidden="true" /> : <MessageCircleOff size={15} aria-hidden="true" />,
              onSelect: () => void toggleComments(),
            }]),
        { label: "Delete", icon: <Trash2 size={15} aria-hidden="true" />, onSelect: remove, danger: true },
      ]
    : [];

  const comments = post.comment_count ?? 0;
  const commentsButton = !post.only_you && (comments > 0 || (signedIn && post.can_comment)) && (
    <button
      type="button"
      className={styles.fiveCount}
      onClick={() => {
        setShowAll(true);
        setFocusKey((key) => key + 1);
      }}
      aria-label={comments ? `${commentCount(comments)}. Show them` : "Comment"}
    >
      <MessageCircle size={15} aria-hidden="true" />
      {comments ? commentCount(comments) : "Comment"}
    </button>
  );

  const when = post.posted_at && (
    <time dateTime={post.posted_at} title={new Date(post.posted_at).toLocaleString("en-CA")}>
      {shortAgo(post.posted_at)}
    </time>
  );

  // In the feed, a suggestion says so and offers a Follow.
  const suggested = post.reason === "suggested";
  // Signed in and someone else's post. Feed authors always have public profiles.
  // In the feed only suggestions offer it (you already follow the rest);
  // elsewhere (a profile's Activity tab) every post does.
  const offersFollow = post.reason === undefined || post.reason === null || suggested;
  const follow = offersFollow && post.author.follow !== null && post.author.follow !== undefined && !post.mine && (
    <FollowButton
      username={post.author.username}
      name={name}
      state={post.author.follow}
      isPrivate={false}
      size="sm"
      onChange={(state) => onChange(post.id, { author: { ...post.author, follow: state } })}
    />
  );

  const head = (
    <>
    {suggested && (
      <p className={styles.suggested}>
        <Sparkles size={13} aria-hidden="true" />
        Suggested for you
      </p>
    )}
    <div className={styles.head}>
      <Link href={profileHref} className={styles.avatarLink} aria-label={`${name}'s profile`}>
        <Avatar path={post.author.avatar_path} name={post.author.display_name ?? post.author.username} email={null} size={44} />
      </Link>
      <div className={styles.who}>
        <span className={styles.nameRow}>
          <Link href={profileHref} className={styles.name}>
            {name}
          </Link>
          {post.hike?.verified && <VerifiedCheck />}
          <AccountBadge label={post.author.label} compact />
        </span>
        <span className={styles.meta}>
          @{post.author.username}
          {when && <> · {when}</>}
        </span>
      </div>
      {follow}
    </div>
    </>
  );

  const highFiveLabel = (
    <>
      <Hand size={17} aria-hidden="true" />
      <span>{post.high_fived ? "High-fived" : "High five"}</span>
    </>
  );

  const actions = (
    <div className={styles.actions}>
      {post.only_you ? null : signedIn && !post.mine ? (
        <button
          type="button"
          className={styles.highFive}
          aria-pressed={post.high_fived}
          onClick={() => void toggleHighFive()}
        >
          {highFiveLabel}
        </button>
      ) : !signedIn ? (
        <Link href={signInHref} className={styles.highFive}>
          {highFiveLabel}
          <span className={ui.srOnly}> (sign in)</span>
        </Link>
      ) : null}
      {!post.only_you && <HighFiveCount post={post} signedIn={signedIn} viewer={viewer} />}
      {commentsButton}
      <span className={styles.spacer} />
      {post.mine ? (
        <MoreMenu label="Post options" items={ownMenu} />
      ) : (
        signedIn && post.author.label !== "official" && (
          <button type="button" className={styles.iconAction} onClick={() => setReporting(true)}>
            <Flag size={15} aria-hidden="true" />
            <span className={styles.reportLabel}>Report</span>
          </button>
        )
      )}
      {reporting && (
        <ReportDialog username={post.author.username} name={name} postId={post.id} onClose={() => setReporting(false)} />
      )}
    </div>
  );

  const footer = (
    <>
      {actions}
      {!post.only_you && (
        <Comments
          post={post}
          signedIn={signedIn}
          signInHref={signInHref}
          open={showAll}
          onOpen={() => {
            setShowAll(true);
            setFocusKey((key) => key + 1);
          }}
          onPost={(change) => onChange(post.id, change)}
          focusKey={focusKey}
        />
      )}
    </>
  );

  const onlyYou = post.review ? (
    <ReviewNotice state={post.review} />
  ) : post.only_you && (
    <p className={styles.onlyYou}>
      <EyeOff size={15} aria-hidden="true" />
      <span>
        {post.unshared ? (
          UNSHARED_LABEL
        ) : (
          <>
            {ONLY_YOU_LABEL}{" "}
            <Link href={sectionHref("privacy")} className={styles.inlineLink}>
              Privacy settings
            </Link>
          </>
        )}
      </span>
    </p>
  );

  if (post.kind === "announcement" && post.announcement) {
    const { announcement } = post;
    const trail = announcement.trail;
    return (
      <li className={`${styles.card} ${styles.cardOfficial}`}>
        {head}
        <p className={styles.announcement}>{announcement.body}</p>
        {announcement.photo_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={announcement.photo_url} alt="" className={styles.photo} loading="lazy" />
        )}
        {trail?.photo && !announcement.photo_url && (
          <Link href={postHref(post)} className={styles.featureLink} aria-label={`Open ${trail.name}`}>
            <TrailPhoto photo={trail.photo} routeMap={trail.route_map} name={trail.name} variant="thumb" />
          </Link>
        )}
        {trail && (
          <Link href={postHref(post)} className={styles.trail}>
            <span className={styles.trailThumb}>
              <TrailPhoto photo={trail.photo} routeMap={trail.route_map} name={trail.name} variant="thumb" mini />
            </span>
            <span className={styles.trailText}>
              <span className={styles.trailName}>{trail.name}</span>
              <span className={styles.trailMeta}>
                {trail.park_name ?? trail.region}
                {" · "}
                {TERRAIN_LABELS[trail.terrain]}
              </span>
            </span>
          </Link>
        )}
        {announcement.source_url && (
          <a href={announcement.source_url} className={styles.source} target="_blank" rel="noopener noreferrer">
            <ExternalLink size={14} aria-hidden="true" />
            <span>
              {announcement.source_label || "Source"}
              {announcement.source_date && <> · {formatSourceDate(announcement.source_date)}</>}
            </span>
            <span className={ui.srOnly}> (opens in a new tab)</span>
          </a>
        )}
        {footer}
      </li>
    );
  }

  if (post.kind !== "hike" || !post.hike) {
    return (
      <li className={`${styles.card} ${post.only_you ? styles.cardOnlyYou : ""}`}>
        {onlyYou}
        {head}
        {post.milestone ? (
          // The badge and its name both open the milestone's card.
          <div className={styles.standalone}>
            <MilestoneBadgeCard badge={post.milestone} owner={name} mine={post.mine} keyboard={false}>
              <MilestoneBadge icon={post.milestone.icon} tier={post.milestone.tier} className={styles.badgeLarge} />
            </MilestoneBadgeCard>
            <span className={styles.standaloneText}>
              <span className={styles.trailLabel}>Milestone earned</span>
              <MilestoneBadgeCard badge={post.milestone} owner={name} mine={post.mine} variant="text">
                <span className={styles.standaloneTitle}>{post.milestone.title}</span>
              </MilestoneBadgeCard>
            </span>
          </div>
        ) : (
          <Link href={postHref(post)} className={`${styles.standalone} ${styles.standaloneLink}`}>
            <RankEmblem level={post.rank?.level ?? 1} className={styles.badgeLarge} />
            <span className={styles.standaloneText}>
              <span className={styles.trailLabel}>New rank</span>
              <span className={styles.standaloneTitle}>{post.rank?.title}</span>
            </span>
          </Link>
        )}
        {footer}
      </li>
    );
  }

  const { hike } = post;
  const trail = hike.trail;
  const place = trail.park_name ?? trail.region;
  const phrases = earnedPhrases(post.earned);
  return (
    <li className={`${styles.card} ${post.only_you ? styles.cardOnlyYou : ""}`}>
      {onlyYou}
      {head}

      <p className={styles.headline}>
        Hiked{" "}
        <Link href={postHref(post)} className={styles.headlineTrail}>
          {trail.name}
        </Link>
        {phrases.map((phrase) => (
          <span key={phrase} className={styles.headlineEarned}>
            {" · "}
            {phrase}
          </span>
        ))}
      </p>
      {post.earned.length > 0 && <EarnedBadges earned={post.earned} owner={name} mine={post.mine} />}

      {hike.note && <p className={styles.note}>{hike.note}</p>}
      {hike.photo_path && (
        <HikePhoto path={hike.photo_path} alt={`${name}'s photo from ${trail.name}`} className={styles.photo} />
      )}

      <Link href={postHref(post)} className={styles.trail}>
        <span className={styles.trailThumb}>
          <TrailPhoto photo={trail.photo} routeMap={trail.route_map} name={trail.name} variant="thumb" mini />
        </span>
        <span className={styles.trailText}>
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
      {footer}
    </li>
  );
}

/**
 * The small badges for what a hike earned. A milestone opens its card (what
 * it takes, when they earned it, where the viewer stands); a rank is a label.
 */
function EarnedBadges({ earned, owner, mine }: { earned: ActivityEarned[]; owner: string; mine: boolean }) {
  return (
    <ul className={styles.earned} aria-label="What this hike earned">
      {earned.map((item) =>
        item.kind === "milestone" && item.milestone ? (
          <li key={`m:${item.milestone.id}`}>
            <MilestoneBadgeCard badge={item.milestone} owner={owner} mine={mine} variant="text">
              <span className={styles.earnedItem}>
                <MilestoneBadge icon={item.milestone.icon} tier={item.milestone.tier} className={styles.badgeSmall} />
                <span>{item.milestone.title}</span>
              </span>
            </MilestoneBadgeCard>
          </li>
        ) : item.rank ? (
          <li key={`r:${item.rank.level}`} className={styles.earnedItem}>
            <RankEmblem level={item.rank.level} className={styles.badgeSmall} />
            <span>{item.rank.title}</span>
          </li>
        ) : null,
      )}
    </ul>
  );
}
