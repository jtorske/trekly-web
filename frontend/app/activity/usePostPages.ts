"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { appendPage, deleteKey, type ActivityPost, type ProfileActivityPage } from "@/lib/activity";
import { useHidden } from "@/lib/useHidden";

export type FetchPostPage = (cursor: string | null, signal?: AbortSignal) => Promise<ProfileActivityPage>;

interface Pages {
  key: string;
  posts: ActivityPost[];
  cursor: string | null;
  done: boolean;
  total: number | null;
  sharing: boolean | null;
}

export interface PostPages {
  /** null until the first page arrives (or after it fails). Includes posts pending delete. */
  posts: ActivityPost[] | null;
  /** All cards, less any pending delete. */
  total: number | null;
  sharing: boolean | null;
  loading: boolean;
  error: string | null;
  done: boolean;
  /** Fetches the next page (or the first again after an error). */
  more: () => void;
  reload: () => void;
  /** A post changed; null drops it (and takes one off the total). */
  update: (id: string, change: Partial<ActivityPost> | null) => void;
  setSharing: (on: boolean) => void;
}

/**
 * A profile's posts, a page at a time. `key` names what's being listed (it
 * restarts from the first page when it changes); null fetches nothing.
 */
export function usePostPages(key: string | null, fetchPage: FetchPostPage): PostPages {
  const [pages, setPages] = useState<Pages | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);
  const [reloads, setReloads] = useState(0);
  const fetchRef = useRef(fetchPage);
  useEffect(() => {
    fetchRef.current = fetchPage;
  });
  const current = key !== null && pages?.key === key ? pages : null;

  const load = useCallback(
    async (cursor: string | null, signal?: AbortSignal) => {
      if (key === null) return;
      setLoading(true);
      setError(null);
      try {
        const page = await fetchRef.current(cursor, signal);
        setPages((prev) => {
          const continuing = cursor !== null && prev?.key === key;
          return {
            key,
            posts: continuing ? appendPage(prev.posts, page.items) : page.items,
            cursor: page.next_cursor,
            done: page.next_cursor === null,
            total: continuing ? prev.total : page.total,
            sharing: continuing ? prev.sharing : page.sharing,
          };
        });
      } catch (caught) {
        if ((caught as { name?: string }).name === "AbortError") return;
        setError({ key, message: caught instanceof Error ? caught.message : "The posts didn't load." });
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [key],
  );

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(null, controller.signal);
    });
    return () => controller.abort();
  }, [key, load, reloads]);

  const update = useCallback((id: string, change: Partial<ActivityPost> | null) => {
    setPages((prev) => {
      if (!prev) return prev;
      if (change === null) {
        if (!prev.posts.some((post) => post.id === id)) return prev;
        return {
          ...prev,
          posts: prev.posts.filter((post) => post.id !== id),
          total: prev.total === null ? null : Math.max(0, prev.total - 1),
        };
      }
      return { ...prev, posts: prev.posts.map((post) => (post.id === id ? { ...post, ...change } : post)) };
    });
  }, []);

  const currentRef = useRef(current);
  useEffect(() => {
    currentRef.current = current;
  });
  // Stable, so an IntersectionObserver effect can depend on it.
  const more = useCallback(() => {
    const now = currentRef.current;
    if (!now) setReloads((n) => n + 1);
    else if (!now.done) void load(now.cursor);
  }, [load]);
  const reload = useCallback(() => setReloads((n) => n + 1), []);
  const setSharing = useCallback(
    (on: boolean) => setPages((prev) => prev && { ...prev, sharing: on }),
    [],
  );

  // Posts waiting on their Undo toast already count as gone.
  const isHidden = useHidden();
  const pending = current?.posts.filter((post) => isHidden(deleteKey(post.id))).length ?? 0;
  const total = current?.total == null ? null : Math.max(0, current.total - pending);

  const shownError = error && error.key === key ? error.message : null;
  return {
    posts: current?.posts ?? null,
    total,
    sharing: current?.sharing ?? null,
    loading,
    error: shownError,
    done: current?.done ?? false,
    more,
    reload,
    update,
    setSharing,
  };
}
