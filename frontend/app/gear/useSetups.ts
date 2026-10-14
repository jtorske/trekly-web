"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { listSetups, type GearSetup } from "@/lib/setupsApi";

/** The signed-in user's named setups, refreshed after any change. */
export function useSetups() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [state, setState] = useState<{ userId: string; setups: GearSetup[]; error: string | null } | null>(null);
  const [token, setToken] = useState(0);

  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    listSetups(controller.signal)
      .then((setups) => setState({ userId, setups, error: null }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setState({ userId, setups: [], error: error instanceof Error ? error.message : "Couldn't load setups." });
      });
    return () => controller.abort();
  }, [userId, token]);

  const current = state && state.userId === userId ? state : null;
  return {
    loading: Boolean(userId) && !current,
    setups: current?.setups ?? [],
    error: current?.error ?? null,
    reload: useCallback(() => setToken((t) => t + 1), []),
  };
}
