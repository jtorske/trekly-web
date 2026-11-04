"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useAuth } from "@/components/AuthProvider";
import { apiFetch } from "./api";
import {
  CACHE_KEY,
  browserTimeZone,
  cachedToday,
  localDate,
  readCache,
  toCache,
  type StreakCounts,
  type VisitReply,
} from "./visitStreak";

/**
 * The signed-in user's visit streak, shared by the profile card and the
 * avatar menu. The first component to mount after sign-in (or app load)
 * records the visit: POST /api/me/visit, unless sessionStorage says today is
 * already recorded. `grew` stays set until one streak icon has played its
 * animation (streakAnimated), so it plays once.
 */
type State = { userId: string | null; streak: StreakCounts | null; grew: boolean };

let state: State = { userId: null, streak: null, grew: false };
const listeners = new Set<() => void>();
let recording: string | null = null;

function set(next: Partial<State>) {
  state = { ...state, ...next };
  for (const listener of listeners) listener();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const snapshot = () => state;
const SERVER_STATE: State = { userId: null, streak: null, grew: false };
const serverSnapshot = () => SERVER_STATE;

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null; // blocked (privacy modes): just call the API
  }
}

async function recordVisit(userId: string) {
  if (recording === userId) return;
  const timeZone = browserTimeZone();
  const today = localDate(new Date(), timeZone);
  const cached = cachedToday(readCache(storage()?.getItem(CACHE_KEY) ?? null), userId, today);
  if (cached) {
    set({ streak: cached, grew: false });
    return;
  }
  recording = userId;
  try {
    const reply = await apiFetch<VisitReply>("/api/me/visit", { method: "POST", auth: true, body: { time_zone: timeZone } });
    if (state.userId !== userId) return;
    try {
      storage()?.setItem(CACHE_KEY, JSON.stringify(toCache(userId, reply)));
    } catch {
      // Full or blocked: the next load calls again, which changes nothing.
    }
    set({ streak: { current: reply.current_streak, longest: reply.longest_streak }, grew: reply.grew });
  } catch {
    // Nothing shown; the next app load tries again.
  } finally {
    if (recording === userId) recording = null;
  }
}

export function streakAnimated() {
  if (state.grew) set({ grew: false });
}

export function useStreak() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const current = useSyncExternalStore(subscribe, snapshot, serverSnapshot);

  useEffect(() => {
    if (state.userId === userId) return;
    set({ userId, streak: null, grew: false });
    if (userId) void recordVisit(userId);
  }, [userId]);

  const mine = current.userId === userId ? current : null;
  return { streak: mine?.streak ?? null, grew: mine?.grew ?? false };
}
