"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { listSavedTrails, saveTrail, unsaveTrail, type SavedTrail } from "./accountApi";

/**
 * The signed-in user's bookmarked trails. Toggling is optimistic (the button
 * flips immediately) and rolls back if the server rejects the change.
 */
export function useSavedTrails() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [state, setState] = useState<{ userId: string; saved: SavedTrail[]; error: string | null } | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [token, setToken] = useState(0);

  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    listSavedTrails(controller.signal)
      .then((saved) => setState({ userId, saved, error: null }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setState({ userId, saved: [], error: error instanceof Error ? error.message : "Couldn't load saved trails." });
      });
    return () => controller.abort();
  }, [userId, token]);

  const current = state && state.userId === userId ? state : null;
  const saved = current?.saved ?? [];
  const savedIds = new Set(saved.map((entry) => entry.trail.id));

  const toggle = useCallback(
    async (trailId: string, makeSaved: boolean): Promise<void> => {
      if (!userId) throw new Error("Sign in to save trails.");
      setPending((p) => new Set(p).add(trailId));
      const snapshot = current?.saved ?? [];
      if (!makeSaved) {
        setState((s) => (s ? { ...s, saved: s.saved.filter((entry) => entry.trail.id !== trailId) } : s));
      }
      try {
        if (makeSaved) {
          const entry = await saveTrail(trailId);
          setState((s) =>
            s ? { ...s, saved: [entry, ...s.saved.filter((e) => e.trail.id !== trailId)] } : { userId, saved: [entry], error: null },
          );
        } else {
          await unsaveTrail(trailId);
        }
      } catch (error) {
        setState((s) => (s ? { ...s, saved: snapshot } : s));
        throw error;
      } finally {
        setPending((p) => {
          const next = new Set(p);
          next.delete(trailId);
          return next;
        });
      }
    },
    [userId, current],
  );

  return {
    loading: Boolean(userId) && !current,
    error: current?.error ?? null,
    saved,
    savedIds,
    pending,
    toggle,
    reload: useCallback(() => setToken((t) => t + 1), []),
  };
}
