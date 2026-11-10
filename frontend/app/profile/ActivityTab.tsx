"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Footprints } from "lucide-react";
import MilestoneBadge from "@/components/MilestoneBadge";
import RankEmblem from "@/components/RankEmblem";
import ui from "@/components/ui.module.css";
import PostCard from "@/app/activity/PostCard";
import feedStyles from "@/app/activity/activity.module.css";
import type { PostPages } from "@/app/activity/usePostPages";
import { sectionHref } from "@/app/settings/settingsSections";
import { activityBlocker, deleteKey, earnedPhrases, postHref, shortAgo, type ActivityPost } from "@/lib/activity";
import { nextQuery } from "@/lib/authLogic";
import { updatePrivacy, type PrivacySettings } from "@/lib/profilesApi";
import { toast } from "@/lib/toast";
import { useHidden } from "@/lib/useHidden";
import { SectionCard } from "./ProfileShell";
import shell from "./shell.module.css";
import styles from "./ActivityTab.module.css";

/** Turns "Share my activity in the feed" on or off from the profile. */
function useShareToggle(pages: PostPages, onPrivacy?: (settings: PrivacySettings) => void) {
  const [saving, setSaving] = useState(false);
  const toggle = async (on: boolean) => {
    setSaving(true);
    try {
      const saved = await updatePrivacy({ share_activity: on });
      onPrivacy?.(saved);
      pages.setSharing(on && activityBlocker(saved) === null);
      toast.success(on ? "Your activity is shared in the feed." : "Your activity is no longer shared.");
    } catch (caught) {
      toast.failure(on ? "turn on sharing" : "turn off sharing", caught);
    } finally {
      setSaving(false);
    }
  };
  return { saving, toggle };
}

/**
 * The profile's Activity tab: that person's posts, newest first, as the
 * Activity feed shows them, loading more as you scroll.
 *
 * The owner (on /profile) sees all of theirs, with a banner while nobody else
 * can. Visitors only ever get this tab when the API opens it (public profile,
 * sharing on), and then only the posts the feed would show them.
 */
export default function ActivityTab({
  pages,
  owner,
  signedIn,
  viewer,
  name,
  privacy = null,
  onPrivacy,
}: {
  pages: PostPages;
  /** The owner's own view (/profile), not their public page. */
  owner: boolean;
  signedIn: boolean;
  /** The signed-in viewer's username (their own high five reads "You"). */
  viewer: string | null;
  name: string;
  /** Owner only: their privacy settings, to tell what's stopping sharing. */
  privacy?: PrivacySettings | null;
  onPrivacy?: (settings: PrivacySettings) => void;
}) {
  const pathname = usePathname();
  const isHidden = useHidden();
  const sentinel = useRef<HTMLDivElement>(null);
  const share = useShareToggle(pages, onPrivacy);
  const { posts, loading, error, done, more } = pages;
  const shown = posts?.filter((post) => !isHidden(deleteKey(post.id))) ?? null;
  const signInHref = `/login${nextQuery(pathname)}`;
  const blocker = owner && privacy ? activityBlocker(privacy) : null;
  // "Share my activity" itself is on, but something else stops it.
  const switchedOn = Boolean(privacy?.share_activity);

  // Infinite scroll: the next page once the end of the list comes into view.
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !posts || done || loading || error) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) more();
      },
      { rootMargin: "400px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [posts, done, loading, error, more]);

  // With nothing posted, the empty state offers the same switch.
  const banner = owner && pages.sharing === false && Boolean(shown?.length) && (
    <div className={`${ui.notice} ${styles.banner}`} role="status">
      <p>
        <strong>Only you can see these.</strong>{" "}
        {blocker && switchedOn ? blocker : "Turn on sharing to post them to the Activity feed."}
      </p>
      {blocker && switchedOn ? (
        <Link href={sectionHref("privacy")} className={ui.secondary}>
          Privacy settings
        </Link>
      ) : (
        <button
          type="button"
          role="switch"
          aria-checked={false}
          className={styles.switch}
          disabled={share.saving || !privacy}
          onClick={() => void share.toggle(true)}
        >
          <span className={styles.track} aria-hidden="true">
            <span className={styles.thumb} />
          </span>
          {share.saving ? "Turning on…" : "Share my activity"}
        </button>
      )}
    </div>
  );

  let body;
  if (!shown && error) {
    body = (
      <div className={feedStyles.empty}>
        <p className={ui.error} role="alert">{error}</p>
        <button type="button" className={ui.secondary} onClick={more}>
          Try again
        </button>
      </div>
    );
  } else if (!shown) {
    body = (
      <ul className={feedStyles.list} aria-busy="true" aria-label="Loading activity">
        {[0, 1].map((n) => (
          <li key={n} className={`${ui.skeleton} ${feedStyles.skeletonCard}`} />
        ))}
      </ul>
    );
  } else if (shown.length === 0) {
    body = owner ? (
      <div className={feedStyles.empty}>
        <span className={styles.emptyIcon} aria-hidden="true">
          <Activity size={24} />
        </span>
        <p className={feedStyles.emptyTitle}>No activity yet</p>
        <p className={feedStyles.emptyText}>
          {pages.sharing
            ? "Log a hike with “Share to Activity” ticked and it shows up here, with any badge or rank it earns."
            : "Share your activity, then log a hike: it shows up here and in the Activity feed, with any badge or rank it earns."}
        </p>
        <div className={feedStyles.emptyActions}>
          <Link href="/journal" className={ui.primary}>
            Log a hike
          </Link>
          {!pages.sharing &&
            (blocker && switchedOn ? (
              <Link href={sectionHref("privacy")} className={ui.secondary}>
                Share your activity
              </Link>
            ) : (
              <button
                type="button"
                className={ui.secondary}
                disabled={share.saving || !privacy}
                onClick={() => void share.toggle(true)}
              >
                {share.saving ? "Turning on…" : "Share your activity"}
              </button>
            ))}
        </div>
      </div>
    ) : (
      <p className={styles.quiet}>No activity yet.</p>
    );
  } else {
    body = (
      <>
        <ul className={feedStyles.list} aria-label={owner ? "Your posts" : `${name}'s posts`}>
          {shown.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              signedIn={signedIn}
              viewer={viewer}
              signInHref={signInHref}
              onChange={pages.update}
            />
          ))}
        </ul>
        <div ref={sentinel} className={feedStyles.sentinel} aria-hidden="true" />
        {loading && <p className={feedStyles.more} role="status">Loading more…</p>}
        {error && (
          <p className={feedStyles.more}>
            <span className={ui.error}>{error}</span>{" "}
            <button type="button" className={ui.ghost} onClick={more}>
              Try again
            </button>
          </p>
        )}
      </>
    );
  }

  return (
    <div className={styles.tab}>
      {banner}
      {body}
    </div>
  );
}

/** One line of the Overview card: badge or trail photo, what happened, when. */
function RecentRow({ post }: { post: ActivityPost }) {
  const what =
    post.kind === "hike" && post.hike ? (
      <>
        Hiked <strong>{post.hike.trail.name}</strong>
        {post.earned.length > 0 && (
          <span className={styles.recentExtra}> · {earnedPhrases(post.earned).join(", ")}</span>
        )}
      </>
    ) : post.kind === "milestone" && post.milestone ? (
      <>
        Earned <strong>{post.milestone.title}</strong>
      </>
    ) : (
      <>
        Reached <strong>{post.rank?.title}</strong>
      </>
    );
  return (
    <li>
      <Link href={postHref(post)} className={styles.recentRow}>
        <span className={styles.recentIcon} aria-hidden="true">
          {post.kind === "hike" && post.hike ? (
            <span className={styles.recentHike}>
              <Footprints size={18} />
            </span>
          ) : post.milestone ? (
            <MilestoneBadge icon={post.milestone.icon} tier={post.milestone.tier} className={styles.recentBadge} />
          ) : (
            <RankEmblem level={post.rank?.level ?? 1} className={styles.recentBadge} />
          )}
        </span>
        <span className={styles.recentText}>{what}</span>
        {post.posted_at && (
          <time className={styles.recentWhen} dateTime={post.posted_at}>
            {shortAgo(post.posted_at)}
          </time>
        )}
      </Link>
    </li>
  );
}

/** The Overview's "Recent activity" card: the latest three posts. */
export function RecentActivityCard({ pages, onSeeAll }: { pages: PostPages; onSeeAll: () => void }) {
  const isHidden = useHidden();
  const recent = pages.posts?.filter((post) => !isHidden(deleteKey(post.id))).slice(0, 3) ?? null;
  return (
    <SectionCard
      id="recent-activity"
      title="Recent activity"
      action={
        <button type="button" className={shell.sectionLink} onClick={onSeeAll}>
          See all →
        </button>
      }
    >
      <div className={styles.tokens}>
      {recent === null ? (
        pages.error ? (
          <p className={styles.quiet}>Your activity didn&apos;t load.</p>
        ) : (
          <div className={`${ui.skeleton} ${styles.recentSkeleton}`} aria-busy="true" aria-label="Loading activity" />
        )
      ) : recent.length === 0 ? (
        <p className={styles.quiet}>
          Nothing yet. Shared hikes, badges and ranks show up here.
        </p>
      ) : (
        <>
          {pages.sharing === false && <p className={styles.recentNote}>Only you can see these.</p>}
          <ul className={styles.recent}>
            {recent.map((post) => (
              <RecentRow key={post.id} post={post} />
            ))}
          </ul>
        </>
      )}
      </div>
    </SectionCard>
  );
}
