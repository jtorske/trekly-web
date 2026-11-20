"use client";

import { useEffect, useRef, useState } from "react";

/** How far (px, after damping) a pull must go to refresh. */
export const PULL_THRESHOLD = 64;
const MAX_PULL = 96;

/**
 * Pull-to-refresh on touch screens, while the page itself scrolls (phones and
 * small tablets; on wide screens the feed column scrolls and a refresh comes
 * from the "New posts" pill instead). Pulling down from the very top by
 * PULL_THRESHOLD calls `onRefresh`. Returns how far the pull is (0 at rest),
 * for the indicator. The browser's own pull-to-refresh, which would reload
 * the whole page, is switched off while this is mounted.
 */
export function usePullToRefresh(onRefresh: () => void, enabled = true): number {
  const [pull, setPull] = useState(0);
  const refresh = useRef(onRefresh);
  useEffect(() => {
    refresh.current = onRefresh;
  });

  useEffect(() => {
    if (!enabled) return;
    const root = document.documentElement;
    const before = root.style.overscrollBehaviorY;
    root.style.overscrollBehaviorY = "contain";
    let startY: number | null = null;
    let distance = 0;

    const onStart = (event: TouchEvent) => {
      // Only from the top, with one finger, and only while the window scrolls
      // (from 1024px the feed column scrolls instead: no pulling there).
      if (window.matchMedia("(min-width: 1024px)").matches) {
        startY = null;
        return;
      }
      const scrolls = document.scrollingElement ?? root;
      startY = event.touches.length === 1 && scrolls.scrollTop <= 0 ? event.touches[0].clientY : null;
      distance = 0;
    };
    const onMove = (event: TouchEvent) => {
      if (startY === null) return;
      const dy = event.touches[0].clientY - startY;
      if (dy <= 0) {
        distance = 0;
        setPull(0);
        return;
      }
      distance = Math.min(MAX_PULL, dy * 0.5);
      setPull(distance);
    };
    const onEnd = () => {
      if (startY !== null && distance >= PULL_THRESHOLD) refresh.current();
      startY = null;
      distance = 0;
      setPull(0);
    };

    window.addEventListener("touchstart", onStart, { passive: true });
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("touchend", onEnd);
    window.addEventListener("touchcancel", onEnd);
    return () => {
      root.style.overscrollBehaviorY = before;
      window.removeEventListener("touchstart", onStart);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
      window.removeEventListener("touchcancel", onEnd);
    };
  }, [enabled]);

  return pull;
}
