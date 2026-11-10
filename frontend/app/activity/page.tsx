"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import { appendPage, deleteKey, type ActivityPost, type ActivityScope } from "@/lib/activity";
import { getActivity } from "@/lib/activityApi";
import { nextQuery } from "@/lib/authLogic";
import { useHidden } from "@/lib/useHidden";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useProfile } from "@/lib/useProfile";
import Composer, { type ComposerHandle } from "./Composer";
import Nudge from "@/components/Nudge";
import { toast } from "@/lib/toast";
import { useNudge } from "@/lib/useNudge";
import PostCard from "./PostCard";
import { HikersYouMightKnow, ProfileCard, RecentlyEarned, TrendingTrails } from "./Sidebar";
import styles from "./activity.module.css";

interface Feed {
  key: string;
  posts: ActivityPost[];
  cursor: string | null;
  done: boolean;
}

/**
 * The Activity page: what hikers have recently done, newest first, loading
 * more as you scroll. Anyone can read it; logging, high fives and reports
 * need an account. The API decides who appears (app/activity.py).
 *
 * From 1280px it's three columns in a one-screen shell, as on the profile:
 * your card on the left, the feed (with "Log a hike" on top) in the middle,
 * trending trails and your latest milestone on the right; only the feed
 * scrolls. From 1024px the card moves to the top of the right column; below
 * that it's one column with the composer folded into a bar.
 */
export default function ActivityPage() {
  const { status } = useAuth();
  const { profile } = useProfile();
  const hikeLogs = useHikeLogs();
  const pathname = usePathname();
  const signedIn = status === "signedIn";
  const [scope, setScope] = useState<ActivityScope>("everyone");
  const [feed, setFeed] = useState<Feed | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<ComposerHandle>(null);
  const isHidden = useHidden();
  const requestKey = `${status}:${scope}`;
  const current = feed?.key === requestKey ? feed : null;
  const province = profile?.home_province ?? null;

  const load = useCallback(
    async (cursor: string | null, signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const page = await getActivity(scope, cursor, signedIn, signal);
        setFeed((prev) => ({
          key: requestKey,
          posts: cursor && prev?.key === requestKey ? appendPage(prev.posts, page.items) : page.items,
          cursor: page.next_cursor,
          done: page.next_cursor === null,
        }));
      } catch (caught) {
        if ((caught as { name?: string }).name === "AbortError") return;
        setError(caught instanceof Error ? caught.message : "The feed didn't load.");
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [scope, signedIn, requestKey],
  );

  // First page whenever the filter or sign-in changes (and after posting, below).
  useEffect(() => {
    if (status === "loading") return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(null, controller.signal);
    });
    return () => controller.abort();
  }, [status, load]);

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

  const update = (id: string, change: Partial<ActivityPost> | null) =>
    setFeed((prev) =>
      prev && {
        ...prev,
        posts: change === null
          ? prev.posts.filter((post) => post.id !== id)
          : prev.posts.map((post) => (post.id === id ? { ...post, ...change } : post)),
      },
    );

  const signInHref = `/login${nextQuery(pathname)}`;
  const openComposer = () => composer.current?.open();
  const posts = current?.posts.filter((post) => !isHidden(deleteKey(post.id))) ?? null;

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
  } else if (!current || !posts) {
    body = (
      <ul className={styles.list} aria-busy="true" aria-label="Loading the feed">
        {[0, 1, 2].map((n) => (
          <li key={n} className={`${ui.skeleton} ${styles.skeletonCard}`} />
        ))}
      </ul>
    );
  } else if (posts.length === 0) {
    body = (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>
          {scope === "province" ? "Nothing from your province yet" : "The trail's quiet right now"}
        </p>
        <p className={styles.emptyText}>
          {scope === "province"
            ? "Hikers from your province appear here once they share their activity and show their home province."
            : "When hikers share a hike or earn a badge, it shows up here. Log a hike and be the first."}
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
          {posts.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              signedIn={signedIn}
              signInHref={signInHref}
              viewer={profile?.username ?? null}
              onChange={update}
            />
          ))}
        </ul>
        <div ref={sentinel} className={styles.sentinel} aria-hidden="true" />
        {loading && <p className={styles.more} role="status">Loading more…</p>}
        {error && (
          <p className={styles.more}>
            <span className={ui.error}>{error}</span>{" "}
            <button type="button" className={ui.ghost} onClick={() => void load(current.cursor)}>
              Try again
            </button>
          </p>
        )}
        {current.done && posts.length > 5 && <p className={styles.more}>You&apos;re all caught up.</p>}
      </>
    );
  }

  const card = (
    <ProfileCard
      profile={profile}
      trailsHiked={signedIn && !hikeLogs.loading ? hikeLogs.logs.length : null}
      signedIn={signedIn}
      signInHref={signInHref}
      onLogHike={openComposer}
    />
  );

  return (
    <main className={styles.page}>
      <div className={styles.columns}>
        <aside className={styles.left} aria-label="You">
          {card}
        </aside>

        <div ref={scroller} className={styles.feedColumn}>
          <div className={styles.feedInner}>
            <h1 className={styles.title}>Activity</h1>
            <Composer
              handle={composer}
              logs={hikeLogs.byTrail}
              save={hikeLogs.save}
              onPosted={() => void load(null)}
              signInHref={signInHref}
            />

            <div className={styles.toolbar}>
              <div className={styles.tabs} role="group" aria-label="Show activity from">
                <button
                  type="button"
                  className={styles.tab}
                  aria-pressed={scope === "everyone"}
                  onClick={() => setScope("everyone")}
                >
                  Everyone
                </button>
                {province && (
                  <button
                    type="button"
                    className={styles.tab}
                    aria-pressed={scope === "province"}
                    onClick={() => setScope("province")}
                  >
                    From my province
                  </button>
                )}
              </div>
            </div>

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

            {body}
          </div>
        </div>

        <aside className={styles.right} aria-label="Around Trekly">
          <div className={styles.rightCard}>{card}</div>
          <TrendingTrails />
          {signedIn && <RecentlyEarned />}
          <HikersYouMightKnow />
        </aside>
      </div>
    </main>
  );
}
