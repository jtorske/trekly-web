"use client";

import { useSyncExternalStore } from "react";

/**
 * Query-string values (?tab=…, ?preview=1) that change without a Next.js
 * navigation. router.replace re-requested the page from the server on every
 * tab click (~1.3 s on /u/[username]); history.pushState doesn't, and Next
 * still keeps its router (and Back/Forward) in step with it.
 *
 * Only the components that read a value re-render when it changes, so the
 * page around them doesn't: a tab click repaints the tab bar and swaps the
 * visible panel, nothing else. Back, Forward and refresh read the URL.
 */

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

function read(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

/** The current path with `name` set to `value` (removed when null). */
export function withParam(name: string, value: string | null): string {
  const params = new URLSearchParams(window.location.search);
  if (value === null) params.delete(name);
  else params.set(name, value);
  const query = params.toString();
  return `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
}

/**
 * Sets `name` in the URL and tells every reader. A new history entry by
 * default (Back returns to the previous tab); `replace` for toggles.
 */
export function setQueryParam(name: string, value: string | null, { replace = false } = {}) {
  if (read(name) === value) return;
  const url = withParam(name, value);
  if (replace) window.history.replaceState(null, "", url);
  else window.history.pushState(null, "", url);
  listeners.forEach((listener) => listener());
}

/** A query-string value; re-renders only when it changes. Null on the server. */
export function useQueryParam(name: string): string | null {
  return useSyncExternalStore(
    subscribe,
    () => read(name),
    () => null,
  );
}
