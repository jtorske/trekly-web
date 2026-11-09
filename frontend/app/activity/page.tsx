"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import { appendPage, type ActivityPost, type ActivityScope } from "@/lib/activity";
import { getActivity } from "@/lib/activityApi";
import { nextQuery } from "@/lib/authLogic";
import { getPrivacy } from "@/lib/profilesApi";
import { useProfile } from "@/lib/useProfile";
import { sectionHref } from "@/app/settings/settingsSections";
import PostCard from "./PostCard";
import styles from "./activity.module.css";

interface Feed {
  key: string;
  posts: ActivityPost[];
  cursor: string | null;
  done: boolean;
}

/**
 * The Activity page: what hikers have recently done, newest first, loading
 * more as you scroll. Anyone can read it; high fives and reports need an
 * account. The API decides who appears (app/activity.py on the backend).
 */
export default function ActivityPage() {
  const { status } = useAuth();
  const { profile } = useProfile();
  const pathname = usePathname();
  const signedIn = status === "signedIn";
  const [scope, setScope] = useState<ActivityScope>("everyone");
  const [feed, setFeed] = useState<Feed | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sharing, setSharing] = useState<boolean | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);
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

  // First page whenever the filter or sign-in changes.
  useEffect(() => {
    if (status === "loading") return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(null, controller.signal);
    });
    return () => controller.abort();
  }, [status, load]);

  // Is the viewer's own activity shared? A gentle pointer to the setting if not.
  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then((settings) => setSharing(settings.share_activity))
      .catch(() => undefined);
    return () => controller.abort();
  }, [signedIn]);

  // Infinite scroll: the next page once the end of the list is near.
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !current || current.done || loading || error) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void load(current.cursor);
      },
      { rootMargin: "600px 0px" },
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
  } else if (!current) {
    body = (
      <ul className={styles.list} aria-busy="true" aria-label="Loading the feed">
        {[0, 1, 2].map((n) => (
          <li key={n} className={`${ui.skeleton} ${styles.skeletonCard}`} />
        ))}
      </ul>
    );
  } else if (current.posts.length === 0) {
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
          <Link href={signedIn ? "/journal" : signInHref} className={ui.primary}>
            Log a hike
          </Link>
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
          {current.posts.map((post) => (
            <PostCard key={post.id} post={post} signedIn={signedIn} signInHref={signInHref} onChange={update} />
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
        {current.done && current.posts.length > 5 && <p className={styles.more}>You&apos;re all caught up.</p>}
      </>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <header className={styles.header}>
          <p className={styles.eyebrow}>Activity</p>
          <h1 className={styles.title}>Out on the trail</h1>
          <p className={styles.lead}>Recent hikes, badges and ranks from hikers who share their activity.</p>
        </header>

        <div className={styles.toolbar}>
          {province && (
            <div className={ui.chips} role="group" aria-label="Show activity from">
              <button
                type="button"
                className={ui.chip}
                aria-pressed={scope === "everyone"}
                onClick={() => setScope("everyone")}
              >
                Everyone
              </button>
              <button
                type="button"
                className={ui.chip}
                aria-pressed={scope === "province"}
                onClick={() => setScope("province")}
              >
                From my province
              </button>
            </div>
          )}
          {signedIn && sharing === false && (
            <p className={styles.shareNote}>
              Your own activity isn&apos;t shared.{" "}
              <Link href={sectionHref("privacy")} className={styles.inlineLink}>
                Turn it on in Privacy settings
              </Link>
            </p>
          )}
        </div>

        {body}
      </div>
    </main>
  );
}
