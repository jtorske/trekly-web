"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import type { ActivityPost } from "@/lib/activity";
import { getPost } from "@/lib/activityApi";
import { ApiError } from "@/lib/api";
import { nextQuery } from "@/lib/authLogic";
import { useProfile } from "@/lib/useProfile";
import PostCard from "../PostCard";
import styles from "../activity.module.css";

/**
 * One post on its own page, every comment open: where comment
 * notifications lead. A post the reader can't see is "not found", whatever
 * the reason (deleted, unshared, private, a block).
 */
export default function PostPage({ id }: { id: string }) {
  const { status } = useAuth();
  const { profile } = useProfile();
  const pathname = usePathname();
  const router = useRouter();
  const signedIn = status === "signedIn";
  const [loaded, setLoaded] = useState<{ key: string; post: ActivityPost | null; error: string | null } | null>(null);
  const key = `${status}:${id}`;
  const current = loaded?.key === key ? loaded : null;

  useEffect(() => {
    if (status === "loading") return;
    const controller = new AbortController();
    getPost(id, signedIn, controller.signal)
      .then((post) => setLoaded({ key, post, error: null }))
      .catch((caught: unknown) => {
        if ((caught as { name?: string }).name === "AbortError") return;
        const missing = caught instanceof ApiError && (caught.status === 404 || caught.status === 422);
        setLoaded({ key, post: null, error: missing ? null : "This post didn't load. Try again in a moment." });
      });
    return () => controller.abort();
  }, [id, key, signedIn, status]);

  const update = (_postId: string, change: Partial<ActivityPost> | null) => {
    if (change === null) {
      // Deleted (after its Undo window).
      router.push("/activity");
      return;
    }
    setLoaded((prev) => (prev?.post ? { ...prev, post: { ...prev.post, ...change } } : prev));
  };

  return (
    <main className={styles.page}>
      <div className={styles.postPage}>
        <Link href="/activity" className={styles.backLink}>
          <span aria-hidden="true">←</span> Activity
        </Link>
        <h1 className={ui.srOnly}>Post</h1>
        {!current ? (
          <div className={styles.skeletonCard} aria-busy="true" aria-label="Loading" />
        ) : current.post ? (
          <ul className={styles.list}>
            <PostCard
              post={current.post}
              signedIn={signedIn}
              signInHref={`/login${nextQuery(pathname)}`}
              viewer={profile?.username ?? null}
              onChange={update}
              commentsOpen
            />
          </ul>
        ) : (
          <div className={styles.postMissing}>
            <p>
              <strong>{current.error ?? "This post isn't available."}</strong>
            </p>
            {!current.error && <p>It may have been deleted, or its author may have stopped sharing it.</p>}
            <Link href="/activity" className={ui.secondary}>
              Back to Activity
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}
