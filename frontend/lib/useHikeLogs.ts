"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { deleteHikeLog, listHikeLogs, putHikeLog, type HikeLog, type HikeLogInput } from "./hikeLogsApi";
import { removeImages } from "./storage";
import { refreshRank } from "./useRank";
import { toast } from "./toast";

/**
 * The signed-in user's Trail Journal entries. Saving or removing an entry
 * also tidies up Storage: a replaced or removed photo is deleted once the
 * entry no longer points at it.
 */
export function useHikeLogs() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [state, setState] = useState<{ userId: string; logs: HikeLog[]; error: string | null } | null>(null);

  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    listHikeLogs(controller.signal)
      .then((logs) => setState({ userId, logs, error: null }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setState({ userId, logs: [], error: error instanceof Error ? error.message : "Couldn't load your journal." });
      });
    return () => controller.abort();
  }, [userId]);

  const current = state && state.userId === userId ? state : null;
  const logs = current?.logs;

  const save = useCallback(
    async (trailId: string, input: HikeLogInput): Promise<HikeLog> => {
      const previous = logs?.find((log) => log.trail.id === trailId);
      const saved = await putHikeLog(trailId, input);
      setState((s) => (s ? { ...s, logs: [saved, ...s.logs.filter((log) => log.trail.id !== trailId)] } : s));
      // Points come from hikes; a new one may be a rank-up to celebrate.
      void refreshRank(previous ? "hike-changed" : "hike-added");
      if (previous) toast.success("Hike log updated");
      else toast.success("Stamped in your Trail Journal", { link: { label: "Open journal", href: "/journal" } });
      if (previous?.photo_path && previous.photo_path !== saved.photo_path) {
        await removeImages("hike-photos", [previous.photo_path]).catch(() => undefined);
      }
      return saved;
    },
    [logs],
  );

  const remove = useCallback(
    async (trailId: string): Promise<void> => {
      const previous = logs?.find((log) => log.trail.id === trailId);
      await deleteHikeLog(trailId);
      setState((s) => (s ? { ...s, logs: s.logs.filter((log) => log.trail.id !== trailId) } : s));
      void refreshRank("hike-changed");
      toast.success("Hike log removed");
      if (previous?.photo_path) await removeImages("hike-photos", [previous.photo_path]).catch(() => undefined);
    },
    [logs],
  );

  return {
    loading: Boolean(userId) && !current,
    error: current?.error ?? null,
    logs: logs ?? [],
    byTrail: new Map((logs ?? []).map((log) => [log.trail.id, log])),
    save,
    remove,
  };
}
