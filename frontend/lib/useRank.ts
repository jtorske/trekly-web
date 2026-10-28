"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useAuth } from "@/components/AuthProvider";
import { shouldCelebrate, type MyRank, type Rank, type RankCause } from "./rank";
import { getMyRank } from "./ranksApi";

/**
 * The signed-in user's rank, shared by everything that shows it (profile
 * card, avatar menu, journal), so one change updates them all. Logging a
 * hike calls refreshRank("hike-added"); if that crosses into a new rank,
 * `celebrating` is set for RankCelebration to play once.
 */
type State = { userId: string | null; rank: MyRank | null; celebrating: Rank | null };

let state: State = { userId: null, rank: null, celebrating: null };
const listeners = new Set<() => void>();
let inFlight: AbortController | null = null;

function set(next: Partial<State>) {
  state = { ...state, ...next };
  for (const listener of listeners) listener();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const snapshot = () => state;
// Cached: React needs the same object every time.
const SERVER_STATE: State = { userId: null, rank: null, celebrating: null };
const serverSnapshot = () => SERVER_STATE;

export async function refreshRank(cause: RankCause): Promise<void> {
  if (!state.userId) return;
  inFlight?.abort();
  const controller = new AbortController();
  inFlight = controller;
  const userId = state.userId;
  try {
    const next = await getMyRank(controller.signal);
    if (state.userId !== userId) return;
    const celebrate = shouldCelebrate(state.rank?.rank ?? null, next.rank, cause);
    set({ rank: next, ...(celebrate ? { celebrating: next.rank } : {}) });
  } catch {
    // Keep what's shown; the next refresh tries again.
  }
}

export function dismissCelebration() {
  set({ celebrating: null });
}

export function useRank() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const current = useSyncExternalStore(subscribe, snapshot, serverSnapshot);

  useEffect(() => {
    if (state.userId === userId) return;
    set({ userId, rank: null, celebrating: null });
    if (userId) void refreshRank("load");
  }, [userId]);

  const mine = current.userId === userId ? current : null;
  return { rank: mine?.rank ?? null, celebrating: mine?.celebrating ?? null, loading: Boolean(userId) && !mine?.rank };
}
