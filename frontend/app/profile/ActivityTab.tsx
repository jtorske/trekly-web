"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Hand } from "lucide-react";
import ui from "@/components/ui.module.css";
import PostCard from "@/app/activity/PostCard";
import feedStyles from "@/app/activity/activity.module.css";
import type { PostPages } from "@/app/activity/usePostPages";
import { sectionHref } from "@/app/settings/settingsSections";
import { activityBlocker, deleteKey, highFivesLabel, postPagePath, type ActivitySummary } from "@/lib/activity";
import { answerPastHikes } from "@/lib/activityApi";
import { nextQuery } from "@/lib/authLogic";
import { updatePrivacy, type PrivacySettings } from "@/lib/profilesApi";
import { toast } from "@/lib/toast";
import { useHidden } from "@/lib/useHidden";
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
 * Asked once, while sharing is on: the hikes only the owner sees (logged
 * before they shared their activity, onboarding, past hikes) can be shared
 * together. Either answer puts it away for good.
 */
function PastHikesPrompt({ pages }: { pages: PostPages }) {
  const [state, setState] = useState<"ask" | "saving" | "done">("ask");
  if (state === "done" || pages.pastHikes === 0) return null;
  const count = pages.pastHikes;
  const hikes = count === 1 ? "1 earlier hike" : `${count} earlier hikes`;
  const answer = async (share: boolean) => {
    setState("saving");
    try {
      const { shared } = await answerPastHikes(share);
      setState("done");
      if (share) {
        toast.success(`Shared ${shared === 1 ? "1 hike" : `${shared} hikes`} on your profile and in the Activity feed.`);
        pages.reload();
      }
    } catch (caught) {
      setState("ask");
      toast.failure(share ? "share your past hikes" : "save that", caught);
    }
  };
  return (
    <div className={`${ui.notice} ${styles.prompt}`} role="region" aria-labelledby="past-hikes-title">
      <div>
        <p id="past-hikes-title" className={styles.promptTitle}>
          Share your past hikes?
        </p>
        <p>
          Only you can see your {hikes}. Share them on your profile and in the Activity feed, with the badges
          they earned. Hikes you unshared stay private.
        </p>
      </div>
      <div className={styles.promptActions}>
        <button type="button" className={ui.primary} disabled={state === "saving"} onClick={() => void answer(true)}>
          {state === "saving" ? "Saving…" : "Share them"}
        </button>
        <button type="button" className={ui.ghost} disabled={state === "saving"} onClick={() => void answer(false)}>
          Not now
        </button>
      </div>
    </div>
  );
}

/**
 * The profile's Activity tab (the first tab): that person's hikes, and the
 * badges and ranks they earned, newest first, as the Activity feed shows
 * them, loading more as you scroll.
 *
 * The owner (on /profile) sees all of theirs, with a banner while nobody else
 * can. Every hike of theirs is here (the API gives the ones they never
 * shared an owner-only post when this tab first loads); visitors only see
 * the shared ones. Visitors only ever get this tab when the API opens it (public profile,
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
        {blocker && switchedOn ? blocker : "Turn on sharing to post your shared hikes to the Activity feed."}
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
            ? "Log a hike and it shows up here and in the Activity feed, with any badge or rank it earns."
            : "Log a hike and it shows up here, with any badge or rank it earns. Share your activity to post it to the Activity feed too."}
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
      <div className={feedStyles.empty}>
        <span className={styles.emptyIcon} aria-hidden="true">
          <Activity size={24} />
        </span>
        <p className={feedStyles.emptyTitle}>No activity yet</p>
        <p className={feedStyles.emptyText}>Hikes they log and badges they earn will show up here.</p>
        <div className={feedStyles.emptyActions}>
          <Link href="/activity" className={ui.secondary}>
            See the Activity feed
          </Link>
        </div>
      </div>
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
      {owner && <PastHikesPrompt pages={pages} />}
      {owner && pages.summary && Boolean(shown?.length) && <HighFiveSummary summary={pages.summary} />}
      {banner}
      {body}
    </div>
  );
}

/** The owner's own tab only: high fives their posts have received, and the top one. */
function HighFiveSummary({ summary }: { summary: ActivitySummary }) {
  const top = summary.top_post;
  return (
    <section className={styles.summary} aria-label="High fives on your posts">
      <Hand size={20} aria-hidden="true" className={styles.summaryIcon} />
      <p className={styles.summaryText}>
        <strong>{summary.high_fives === 0 ? "No high fives yet" : highFivesLabel(summary.high_fives)}</strong>
        {summary.high_fives === 0 ? (
          <span> When hikers high-five your posts, you&apos;ll see the total here.</span>
        ) : (
          <span>
            {" "}
            received in all.
            {top && (
              <>
                {" "}
                Most: <Link href={postPagePath(top.id)} className={styles.summaryLink}>{top.title}</Link> ({top.high_fives}).
              </>
            )}
          </span>
        )}
      </p>
    </section>
  );
}
