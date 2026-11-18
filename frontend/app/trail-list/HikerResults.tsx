"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { UserRound } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import HikerRow from "@/components/social/HikerRow";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { nextQuery } from "@/lib/authLogic";
import { MIN_QUERY, isSearchable, searchHref, searchTerm, type HikerPage } from "@/lib/hikerSearch";
import { searchHikers } from "@/lib/hikerSearchApi";
import styles from "./HikerResults.module.css";

const isAbort = (error: unknown) => (error as { name?: string }).name === "AbortError";

/** Explore's Hikers tab: people search, signed in only. */
export default function HikerResults({ q }: { q: string }) {
  const { status } = useAuth();
  const term = searchTerm(q);
  const searchable = isSearchable(q);
  const [pages, setPages] = useState<{ q: string; page: HikerPage } | null>(null);
  const [error, setError] = useState<{ q: string; message: string } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const signedIn = status === "signedIn";

  useEffect(() => {
    if (!signedIn || !searchable) return;
    const controller = new AbortController();
    searchHikers(term, { signal: controller.signal })
      .then((page) => {
        setPages({ q: term, page });
        setError(null);
      })
      .catch((caught: unknown) => {
        if (isAbort(caught)) return;
        setError({ q: term, message: caught instanceof ApiError ? caught.message : "We couldn't search just now." });
      });
    return () => controller.abort();
  }, [signedIn, searchable, term, attempt]);

  const loadMore = async () => {
    if (!pages?.page.next_offset) return;
    setLoadingMore(true);
    try {
      const next = await searchHikers(pages.q, { offset: pages.page.next_offset });
      setPages((current) =>
        current && current.q === pages.q
          ? { q: current.q, page: { items: [...current.page.items, ...next.items], next_offset: next.next_offset } }
          : current,
      );
    } catch (caught) {
      setError({ q: pages.q, message: caught instanceof ApiError ? caught.message : "We couldn't load more just now." });
    } finally {
      setLoadingMore(false);
    }
  };

  if (status === "loading") return <div className={`${ui.skeleton} ${styles.rowSkeleton}`} />;
  if (!signedIn) {
    return (
      <div className={styles.hint}>
        <UserRound size={28} aria-hidden="true" className={styles.hintIcon} />
        <p>Sign in to find other hikers and follow them.</p>
        <div className={styles.hintActions}>
          <Link href={`/login${nextQuery(searchHref("hikers", q))}`} className={ui.primary}>
            Sign in
          </Link>
          <Link href="/signup" className={ui.secondary}>
            Create an account
          </Link>
        </div>
      </div>
    );
  }
  if (!searchable) {
    return (
      <p className={styles.hint}>
        {term ? `Type at least ${MIN_QUERY} characters.` : "Search for hikers by name or username."}
      </p>
    );
  }
  if (error?.q === term && pages?.q !== term) {
    return (
      <div className={styles.hint} role="alert">
        <p>{error.message}</p>
        <button type="button" className={ui.secondary} onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  if (!pages) {
    return (
      <div aria-busy="true" aria-label="Loading hikers">
        {[0, 1, 2].map((n) => (
          <div key={n} className={`${ui.skeleton} ${styles.rowSkeleton}`} />
        ))}
      </div>
    );
  }
  const stale = pages.q !== term;
  if (pages.page.items.length === 0) {
    return (
      <div className={`${styles.hint} ${stale ? styles.stale : ""}`}>
        <p>No hikers match &ldquo;{pages.q}&rdquo;.</p>
        <p className={styles.small}>Private profiles only appear if their owner lets people find them.</p>
      </div>
    );
  }
  return (
    <>
      <ul className={`${styles.people} ${stale ? styles.stale : ""}`} aria-label="Hikers">
        {pages.page.items.map((hiker) => (
          <HikerRow key={hiker.username} hiker={hiker} />
        ))}
      </ul>
      {error?.q === pages.q && (
        <p className={ui.error} role="alert">
          {error.message}
        </p>
      )}
      {pages.page.next_offset !== null && !stale && (
        <div className={styles.more}>
          <button type="button" className={ui.secondary} onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Show more"}
          </button>
        </div>
      )}
    </>
  );
}
