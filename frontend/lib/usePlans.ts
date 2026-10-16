"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { plansApi, type TripPlanSummary } from "./plansApi";

/** The signed-in user's trip plans, soonest first. */
export function usePlans() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [state, setState] = useState<{ userId: string; plans: TripPlanSummary[]; error: string | null } | null>(null);
  const [token, setToken] = useState(0);

  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    plansApi
      .list(controller.signal)
      .then((plans) => setState({ userId, plans, error: null }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setState({ userId, plans: [], error: error instanceof Error ? error.message : "Couldn't load trip plans." });
      });
    return () => controller.abort();
  }, [userId, token]);

  const current = state && state.userId === userId ? state : null;
  return {
    loading: Boolean(userId) && !current,
    plans: current?.plans ?? [],
    error: current?.error ?? null,
    reload: useCallback(() => setToken((t) => t + 1), []),
  };
}
