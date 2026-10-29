"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { listSavedTrails, saveTrail, unsaveTrail, type SavedTrail } from "./accountApi";
import { toast } from "./toast";
import { isPendingRemoval, removeWithUndo, reveal } from "./undo";
import { useHidden } from "./useHidden";

const savedKey = (trailId: string) => `saved:${trailId}`;

/**
 * The signed-in user's bookmarked trails. Saving toasts once the server
 * confirms; removing hides the trail at once and offers Undo, and the delete
 * only goes out when that toast closes (see lib/undo).
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

  const isHidden = useHidden();
  const current = state && state.userId === userId ? state : null;
  const saved = (current?.saved ?? []).filter((entry) => !isHidden(savedKey(entry.trail.id)));
  const savedIds = new Set(saved.map((entry) => entry.trail.id));

  const toggle = useCallback(
    async function run(trailId: string, makeSaved: boolean): Promise<void> {
      if (!userId) throw new Error("Sign in to save trails.");
      const key = savedKey(trailId);
      if (!makeSaved) {
        // Hidden now; the delete waits for the Undo toast to close.
        removeWithUndo({
          key,
          message: "Removed from saved",
          what: "remove the trail from saved",
          commit: () => unsaveTrail(trailId),
          onCommitted: () => setState((s) => (s ? { ...s, saved: s.saved.filter((entry) => entry.trail.id !== trailId) } : s)),
        });
        return;
      }
      // Saving again before the Undo toast closes: the delete never went out.
      if (isPendingRemoval(key)) {
        reveal(key);
        toast.success("Trail saved", { link: { label: "View saved", href: "/profile?tab=trails" } });
        return;
      }
      reveal(key);
      setPending((p) => new Set(p).add(trailId));
      try {
        const entry = await saveTrail(trailId);
        setState((s) =>
          s ? { ...s, saved: [entry, ...s.saved.filter((e) => e.trail.id !== trailId)] } : { userId, saved: [entry], error: null },
        );
        toast.success("Trail saved", { link: { label: "View saved", href: "/profile?tab=trails" } });
      } catch (error) {
        toast.failure("save the trail", error, () => void run(trailId, true).catch(() => undefined));
        throw error;
      } finally {
        setPending((p) => {
          const next = new Set(p);
          next.delete(trailId);
          return next;
        });
      }
    },
    [userId],
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
