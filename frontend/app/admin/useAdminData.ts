"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Loaded<T> =
  | { status: "loading"; data?: T }
  | { status: "error"; message: string; data?: T }
  | { status: "ready"; data: T };

type Settled<T> = { key: string; data?: T; error?: string };

// The last data for each key, so going back to an admin tab shows it at once
// (as "loading", refreshed in the background) instead of a skeleton.
const lastData = new Map<string, unknown>();

/**
 * Load admin data whenever `key` changes; earlier requests are aborted so
 * a slow page can't overwrite a newer one. While reloading, the previous
 * data stays on screen (also the last visit's, when the page opens again).
 * `reload()` refetches after an action.
 */
export function useAdminData<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(() =>
    lastData.has(key) ? { key: "", data: lastData.get(key) as T } : null,
  );
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  const requestKey = `${key}#${nonce}`;

  useEffect(() => {
    const controller = new AbortController();
    loadRef
      .current(controller.signal)
      .then((data) => {
        lastData.set(key, data);
        setSettled({ key: requestKey, data });
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setSettled((current) => ({
          key: requestKey,
          data: current?.data,
          error: error instanceof Error ? error.message : "That didn't load.",
        }));
      });
    return () => controller.abort();
  }, [key, requestKey]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  let state: Loaded<T>;
  if (!settled || settled.key !== requestKey) state = { status: "loading", data: settled?.data };
  else if (settled.error !== undefined) state = { status: "error", message: settled.error, data: settled.data };
  else state = { status: "ready", data: settled.data as T };
  return { state, reload };
}
