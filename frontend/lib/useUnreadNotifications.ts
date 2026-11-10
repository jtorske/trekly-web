"use client";

import { useEffect, useState } from "react";
import { onUnreadChanged } from "./notifications";
import { getUnreadCount } from "./notificationsApi";

const POLL_MS = 60_000;

/**
 * The unread count for the bell: fetched when signed in, again every minute
 * while the tab is visible and whenever it regains focus, and updated at once
 * when the list marks things read. null until known (or when signed out).
 */
export function useUnreadNotifications(signedIn: boolean): number | null {
  const [unread, setUnread] = useState<number | null>(null);

  useEffect(() => {
    if (!signedIn) return;
    let controller = new AbortController();
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      controller.abort();
      controller = new AbortController();
      getUnreadCount(controller.signal)
        .then((body) => setUnread(body.unread))
        // The badge is a hint; a failed check just keeps the last count.
        .catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    const stop = onUnreadChanged(setUnread);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
      stop();
    };
  }, [signedIn]);

  return signedIn ? unread : null;
}
