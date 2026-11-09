"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useAuth } from "@/components/AuthProvider";
import { categorySlug, newlyEarned, type Milestones } from "./milestones";
import { getMyMilestones } from "./milestonesApi";
import { toast } from "./toast";

/**
 * The signed-in user's milestones, shared by the journal, the featured-badge
 * picker and the watcher in the root layout. Anything that can earn one
 * (a hike, a plan, an alert, a setup) calls refreshMilestones(); a milestone
 * earned since the user last heard gets one toast, on this device.
 */
type State = { userId: string | null; data: Milestones | null };

let state: State = { userId: null, data: null };
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
const SERVER_STATE: State = { userId: null, data: null };
const serverSnapshot = () => SERVER_STATE;

const seenKey = (userId: string) => `trekly:milestones-seen:${userId}`;

/** Milestones this user has been told about; null if never recorded (or storage is blocked). */
function readSeen(userId: string): Set<string> | null {
  try {
    const raw = window.localStorage.getItem(seenKey(userId));
    const ids = raw == null ? null : JSON.parse(raw);
    return Array.isArray(ids) ? new Set(ids) : null;
  } catch {
    return null;
  }
}

function writeSeen(userId: string, ids: Set<string>) {
  try {
    window.localStorage.setItem(seenKey(userId), JSON.stringify([...ids]));
  } catch {
    // Storage blocked: no toasts, which is harmless.
  }
}

/**
 * Toast what's new since last time, then remember it. The first time only
 * sets the baseline; `quiet` remembers without toasting (onboarding shows its
 * own summary).
 */
function announce(userId: string, data: Milestones, quiet: boolean) {
  const seen = readSeen(userId);
  for (const milestone of quiet ? [] : newlyEarned(data, seen)) {
    toast.success(`Milestone earned: ${milestone.title}`, {
      link: { label: "See it", href: `/journal?section=${categorySlug(data, milestone.category)}` },
    });
  }
  const earned = data.milestones.flatMap((m) => (m.earned && m.id ? [m.id] : []));
  writeSeen(userId, new Set([...(seen ?? []), ...earned]));
}

export async function refreshMilestones({ quiet = false }: { quiet?: boolean } = {}): Promise<void> {
  if (!state.userId) return;
  inFlight?.abort();
  const controller = new AbortController();
  inFlight = controller;
  const userId = state.userId;
  try {
    const data = await getMyMilestones(controller.signal);
    if (state.userId !== userId) return;
    set({ data });
    announce(userId, data, quiet);
  } catch {
    // Keep what's shown; the next refresh tries again.
  }
}

/** Pass a request through, refreshing milestones once it succeeds. */
export function thenRefreshMilestones<T>(request: Promise<T>): Promise<T> {
  return request.then((result) => {
    void refreshMilestones();
    return result;
  });
}

export function useMilestones() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const current = useSyncExternalStore(subscribe, snapshot, serverSnapshot);

  useEffect(() => {
    if (state.userId === userId) return;
    set({ userId, data: null });
    if (userId) void refreshMilestones();
  }, [userId]);

  const mine = current.userId === userId ? current : null;
  return { milestones: mine?.data ?? null, loading: Boolean(userId) && !mine?.data };
}
