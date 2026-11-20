"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowUp, RefreshCw } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import {
  deleteKey, feedRows, mergeFeedPage, type ActivityPost, type FeedState,
  postPagePath,
} from "@/lib/activity";
import { getActivity, getNewPosts } from "@/lib/activityApi";
import { nextQuery } from "@/lib/authLogic";
import type { HikerResult } from "@/lib/hikerSearch";
import { province as provinceFor } from "@/lib/provinces";
import { useHidden } from "@/lib/useHidden";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useProfile } from "@/lib/useProfile";
import Composer, { type ComposerHandle } from "./Composer";
import Nudge from "@/components/Nudge";
import { toast } from "@/lib/toast";
import { useNudge } from "@/lib/useNudge";
import FollowPrompt from "./FollowPrompt";
import PickCard from "./PickCard";
import PostCard from "./PostCard";
import FindHikers from "./FindHikers";
import { HikersYouMightKnow, ProfileCard, RecentlyEarned, TrendingTrails } from "./Sidebar";
import { PULL_THRESHOLD, usePullToRefresh } from "./usePullToRefresh";
import styles from "./activity.module.css";

interface Feed extends FeedState {
  /** Whose feed this is ("signedIn" / "signedOut"); a sign-in change starts over. */
  key: string;
  cursor: string | null;
  done: boolean;
  asOf: string;
  followsAnyone: boolean;
  hikers: HikerResult[] | null;
}

type ComposerSlot = "left" | "right" | "feed";
const WIDE = "(min-width: 1280px)";
const MEDIUM = "(min-width: 1024px)";

function subscribeToWidth(onChange: () => void) {
  const queries = [window.matchMedia(WIDE), window.matchMedia(MEDIUM)];
  queries.forEach((query) => query.addEventListener("change", onChange));
  return () => queries.forEach((query) => query.removeEventListener("change", onChange));
}

/**
 * Where "Log a hike" goes: under your card in the left column from 1280px,
 * under it at the top of the right column from 1024px (no left column
 * there), and a bar at the top of the feed below that. One composer, so a
 * draft isn't split between copies; null until the width is known.
 */
function useComposerSlot(): ComposerSlot | null {
  return useSyncExternalStore<ComposerSlot | null>(
    subscribeToWidth,
    () => (window.matchMedia(WIDE).matches ? "left" : window.matchMedia(MEDIUM).matches ? "right" : "feed"),
    () => null,
  );
}

/** How often to check for new posts from people you follow, while the tab is visible. */
const NEW_POSTS_EVERY_MS = 60_000;
const PROMPT_DISMISSED = "trekly.activity.followPromptDismissed";

/**
 * The Activity page: one feed, arranged by the API (backend app/feed.py):
 * posts from people you follow first, a "You're all caught up" divider, then
 * suggested posts, with @trekly posts and Trekly picks mixed in. Anyone can
 * read it; logging, high fives and follows need an account.
 *
 * It loads more as you scroll; a "New posts" pill appears when people you
 * follow post, and on phones pulling down from the top refreshes.
 *
 * From 1280px it's three columns in a one-screen shell, as on the profile:
 * your card and "Log a hike" on the left, the feed alone in the middle,
 * trending trails and your latest milestone on the right; each column
 * scrolls on its own. From 1024px the card and composer move to the top of
 * the right column; below that it's one column with the composer folded
 * into a bar at the top of the feed.
 */
export default function ActivityPage() {
  const { status } = useAuth();
  const { profile } = useProfile();
  const hikeLogs = useHikeLogs();
  const pathname = usePathname();
  const signedIn = status === "signedIn";
  const [feed, setFeed] = useState<Feed | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newCount, setNewCount] = useState(0);
  const [promptDismissed, setPromptDismissed] = useState(
    () => typeof window !== "undefined" && window.localStorage.getItem(PROMPT_DISMISSED) === "1",
  );
  const busy = useRef(false);
  const sentinel = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<ComposerHandle>(null);
  const isHidden = useHidden();
  const slot = useComposerSlot();
  const current = feed?.key === status ? feed : null;
  const router = useRouter();

  // Old comment notifications linked to /activity?post=ID: that's the post's own page now.
  useEffect(() => {
    const postId = new URLSearchParams(window.location.search).get("post");
    if (postId) router.replace(postPagePath(postId));
  }, [router]);

  /** A page of the feed: the first (starting over) when `cursor` is null. */
  const load = useCallback(
    async (cursor: string | null, signal?: AbortSignal) => {
      if (busy.current) return;
      busy.current = true;
      setLoading(true);
      setError(null);
      try {
        const page = await getActivity(cursor, signedIn, signal);
        setFeed((prev) => {
          const continuing = cursor !== null && prev?.key === status;
          const merged = mergeFeedPage(continuing ? prev : null, page);
          return {
            ...merged,
            key: status,
            cursor: page.next_cursor,
            done: page.next_cursor === null,
            asOf: continuing ? prev.asOf : page.as_of,
            followsAnyone: page.follows_anyone,
            hikers: continuing ? prev.hikers : page.suggested_hikers,
          };
        });
        if (cursor === null) setNewCount(0);
      } catch (caught) {
        if ((caught as { name?: string }).name === "AbortError") return;
        setError(caught instanceof Error ? caught.message : "The feed didn't load.");
      } finally {
        busy.current = false;
        setLoading(false);
      }
    },
    [status, signedIn],
  );

  // The first page once sign-in is known, and again whenever it changes.
  const decided = status !== "loading";
  const cached = Boolean(current);
  useEffect(() => {
    if (!decided || cached) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(null, controller.signal);
    });
    return () => {
      controller.abort();
      busy.current = false;
    };
  }, [decided, cached, load]);

  /** Starts the feed over from the top (pull to refresh, the pill, a new post of yours). */
  const refresh = useCallback(async () => {
    setRefreshing(true);
    const column = scroller.current;
    if (column && getComputedStyle(column).overflowY === "auto") column.scrollTo({ top: 0, behavior: "smooth" });
    else window.scrollTo({ top: 0, behavior: "smooth" });
    await load(null);
    setRefreshing(false);
  }, [load]);

  const pull = usePullToRefresh(() => void refresh(), decided);

  // "New posts": a quiet check every minute while the tab is in view.
  const asOf = current?.asOf ?? null;
  const watch = signedIn && Boolean(current?.followsAnyone) && asOf !== null;
  useEffect(() => {
    if (!watch || !asOf) return;
    const controller = new AbortController();
    const check = () => {
      if (document.visibilityState !== "visible") return;
      getNewPosts(asOf, controller.signal).then((body) => setNewCount(body.count), () => undefined);
    };
    const handle = window.setInterval(check, NEW_POSTS_EVERY_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      controller.abort();
      window.clearInterval(handle);
      document.removeEventListener("visibilitychange", check);
    };
  }, [watch, asOf]);

  // Not sharing yet? A small card offers the setting until they put it away
  // or turn it on (the API decides; it never shows to guests).
  const nudge = useNudge("activity_card");
  const turnOnSharing = async () => {
    if (await nudge.turnOn()) toast.success("Sharing is on. Tick “Share to Activity” when you log a hike.");
  };

  // Infinite scroll: the next page once the end of the list is near. On wide
  // screens the feed column scrolls rather than the page, so watch inside it.
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !current || current.done || loading || error) return;
    const column = scroller.current;
    const root = column && getComputedStyle(column).overflowY === "auto" ? column : null;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void load(current.cursor);
      },
      { root, rootMargin: "600px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [current, loading, error, load]);

  /** A post changed (null: it's gone). A follow change applies to all of that author's posts. */
  const update = (id: string, change: Partial<ActivityPost> | null) =>
    setFeed((prev) => {
      if (!prev || !prev.posts[id]) return prev;
      const posts = { ...prev.posts };
      if (change === null) {
        delete posts[id];
        return { ...prev, posts, entries: prev.entries.filter((e) => e.type !== "post" || e.post_id !== id) };
      }
      const author = prev.posts[id].author.username;
      for (const [key, post] of Object.entries(posts)) {
        if (key === id) posts[key] = { ...post, ...change };
        else if (change.author && post.author.username === author) {
          posts[key] = { ...post, author: { ...post.author, follow: change.author.follow } };
        }
      }
      return { ...prev, posts };
    });

  const dismissPrompt = () => {
    window.localStorage.setItem(PROMPT_DISMISSED, "1");
    setPromptDismissed(true);
  };

  const signInHref = `/login${nextQuery(pathname)}`;
  const openComposer = () => composer.current?.open();
  const showPrompt =
    signedIn && !promptDismissed && Boolean(current && !current.followsAnyone && current.hikers?.length);
  const rows = current
    ? feedRows(current, { hidden: (postId) => isHidden(deleteKey(postId)), followPrompt: showPrompt })
    : null;
  const place = provinceFor(profile?.home_province ?? null)?.name ?? null;

  let body;
  if (!current && error) {
    body = (
      <div className={styles.empty}>
        <p className={ui.error} role="alert">{error}</p>
        <button type="button" className={ui.secondary} onClick={() => void load(null)}>
          Try again
        </button>
      </div>
    );
  } else if (!current || !rows) {
    body = (
      <ul className={styles.list} aria-busy="true" aria-label="Loading the feed">
        {[0, 1, 2].map((n) => (
          <li key={n} className={styles.skeletonPost} aria-hidden="true">
            <span className={styles.skeletonHead}>
              <span className={`${ui.skeleton} ${styles.skeletonAvatar}`} />
              <span className={styles.skeletonLines}>
                <span className={`${ui.skeleton} ${styles.skeletonLine}`} />
                <span className={`${ui.skeleton} ${styles.skeletonLineShort}`} />
              </span>
            </span>
            <span className={`${ui.skeleton} ${styles.skeletonLine}`} />
            <span className={`${ui.skeleton} ${styles.skeletonMedia}`} />
          </li>
        ))}
      </ul>
    );
  } else if (rows.length === 0) {
    body = (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>The trail&apos;s quiet right now</p>
        <p className={styles.emptyText}>
          When hikers share a hike or earn a badge, it shows up here. Log a hike and be the first.
        </p>
        <div className={styles.emptyActions}>
          {signedIn ? (
            <button type="button" className={ui.primary} onClick={openComposer}>
              Log a hike
            </button>
          ) : (
            <Link href={signInHref} className={ui.primary}>
              Log a hike
            </Link>
          )}
          <Link href="/trail-list" className={ui.secondary}>
            Explore trails
          </Link>
        </div>
      </div>
    );
  } else {
    body = (
      <>
        <ul className={styles.list}>
          {rows.map((row) => {
            if (row.type === "pick") return <PickCard key={row.key} pick={row.pick} />;
            if (row.type === "follow_prompt") {
              return <FollowPrompt key={row.key} hikers={current.hikers ?? []} place={place} onDismiss={dismissPrompt} />;
            }
            if (row.type === "caught_up") {
              return (
                <li key={row.key} className={styles.caughtUp}>
                  <span className={styles.caughtUpText}>
                    <strong>You&apos;re all caught up</strong>
                    <span>You&apos;ve seen the latest from the hikers you follow. Here&apos;s more from around Trekly.</span>
                  </span>
                </li>
              );
            }
            return (
              <PostCard
                key={row.key}
                post={row.post}
                signedIn={signedIn}
                signInHref={signInHref}
                viewer={profile?.username ?? null}
                onChange={update}
              />
            );
          })}
        </ul>
        <div ref={sentinel} className={styles.sentinel} aria-hidden="true" />
        {loading && !refreshing && <p className={styles.more} role="status">Loading more…</p>}
        {error && (
          <p className={styles.more}>
            <span className={ui.error}>{error}</span>{" "}
            <button type="button" className={ui.ghost} onClick={() => void load(current.cursor)}>
              Try again
            </button>
          </p>
        )}
        {current.done && rows.length > 5 && <p className={styles.more}>That&apos;s everything for now.</p>}
      </>
    );
  }

  const card = (
    <ProfileCard
      profile={profile}
      trailsHiked={signedIn && !hikeLogs.loading ? hikeLogs.logs.length : null}
      signedIn={signedIn}
      signInHref={signInHref}
    />
  );
  const composerFor = (where: ComposerSlot) =>
    slot === where &&
    // Guests' card beside it already invites them to sign in.
    (where === "feed" || signedIn) && (
      <Composer
        handle={composer}
        logs={hikeLogs.byTrail}
        save={hikeLogs.save}
        onPosted={() => void refresh()}
        signInHref={signInHref}
        placement={where === "feed" ? "feed" : "side"}
      />
    );

  return (
    <main className={styles.page}>
      <div className={styles.columns}>
        <aside className={styles.left} aria-label="You">
          {card}
          {composerFor("left")}
        </aside>

        <div ref={scroller} className={styles.feedColumn}>
          <div className={styles.feedInner}>
            {(pull > 0 || refreshing) && (
              <div
                className={styles.pullIndicator}
                style={{ height: refreshing ? PULL_THRESHOLD * 0.6 : pull * 0.6 }}
                role={refreshing ? "status" : undefined}
              >
                <RefreshCw
                  size={20}
                  aria-hidden="true"
                  className={refreshing ? styles.spinning : undefined}
                  style={refreshing ? undefined : { transform: `rotate(${(pull / PULL_THRESHOLD) * 270}deg)` }}
                />
                <span className={ui.srOnly}>{refreshing ? "Refreshing the feed" : "Pull to refresh"}</span>
              </div>
            )}
            <h1 className={styles.title}>Activity</h1>
            {composerFor("feed")}

            {newCount > 0 && (
              <div className={styles.newPostsBar}>
                <button type="button" className={styles.newPosts} onClick={() => void refresh()}>
                  <ArrowUp size={16} aria-hidden="true" />
                  {newCount === 1 ? "1 new post" : `${newCount} new posts`}
                </button>
              </div>
            )}

            {nudge.show && (
              <Nudge
                card
                action="Turn on sharing"
                busy={nudge.busy}
                onTurnOn={() => void turnOnSharing()}
                onDismiss={nudge.dismiss}
                className={styles.nudge}
              >
                You&apos;re not sharing yet. Your hikes and badges could appear here.
              </Nudge>
            )}

            <div className={styles.feedBody}>{body}</div>
          </div>
        </div>

        <aside className={styles.right} aria-label="Around Trekly">
          <div className={styles.rightCard}>
            {card}
            {composerFor("right")}
          </div>
          {signedIn && <FindHikers />}
          <TrendingTrails />
          {signedIn && <RecentlyEarned />}
          <HikersYouMightKnow signedIn={signedIn} homeProvince={profile?.home_province ?? null} />
        </aside>
      </div>
    </main>
  );
}
