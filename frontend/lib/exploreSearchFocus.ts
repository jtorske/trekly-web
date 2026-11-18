/**
 * The phone menu's Explore row puts the cursor in Explore's search box. The
 * menu is a modal dialog, so nothing behind it can take focus until it has
 * closed, and Explore may not have mounted yet either: whichever comes last
 * (the menu closing or Explore mounting) does the focusing.
 */

export const EXPLORE_SEARCH_ID = "explore-search";

/** A request older than this is dropped, so a later visit doesn't grab focus. */
const STALE_MS = 5000;
let requestedAt = 0;

export function requestExploreSearchFocus(): void {
  requestedAt = Date.now();
}

export function exploreSearchFocusPending(): boolean {
  return requestedAt > 0 && Date.now() - requestedAt < STALE_MS;
}

/** Focuses the box if a request is pending and the box is there to take it. */
export function focusExploreSearch(): boolean {
  if (!exploreSearchFocusPending()) return false;
  const input = document.getElementById(EXPLORE_SEARCH_ID);
  if (!input) return false;
  input.focus({ preventScroll: true });
  if (document.activeElement !== input) return false;
  requestedAt = 0;
  return true;
}
