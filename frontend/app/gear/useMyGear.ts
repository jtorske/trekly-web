"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { listMyGear, type GearItem } from "@/lib/gearApi";

type State =
  | { status: "idle" | "loading"; items: GearItem[]; error: null }
  | { status: "ready"; items: GearItem[]; error: null }
  | { status: "error"; items: GearItem[]; error: string };

/**
 * The signed-in user's saved gear, loaded from the API (the source of truth
 * for both the mat and the list). Mutations update local state only after the
 * server confirms them, so the UI never shows an unsaved item as owned.
 */
export function useMyGear() {
  const { status: authStatus, user } = useAuth();
  const userId = user?.id ?? null;
  const [state, setState] = useState<State & { userId: string | null }>({
    status: "idle",
    items: [],
    error: null,
    userId: null,
  });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    listMyGear(controller.signal)
      .then((collection) => setState({ status: "ready", items: collection.items, error: null, userId }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setState({
          status: "error",
          items: [],
          error: error instanceof Error ? error.message : "Couldn't load your gear.",
          userId,
        });
      });
    return () => controller.abort();
  }, [userId, reloadToken]);

  const current = state.userId === userId ? state : null;
  const status: "signedOut" | "loading" | "ready" | "error" =
    authStatus === "loading"
      ? "loading"
      : !userId
        ? "signedOut"
        : !current || current.status === "idle" || current.status === "loading"
          ? "loading"
          : current.status;

  const upsert = useCallback(
    (item: GearItem) =>
      setState((previous) => {
        const exists = previous.items.some((existing) => existing.id === item.id);
        return {
          ...previous,
          items: exists
            ? previous.items.map((existing) => (existing.id === item.id ? item : existing))
            : [...previous.items, item],
        } as typeof previous;
      }),
    [],
  );
  const remove = useCallback(
    (id: string) =>
      setState((previous) => ({ ...previous, items: previous.items.filter((item) => item.id !== id) }) as typeof previous),
    [],
  );
  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return {
    status,
    items: status === "ready" ? (current?.items ?? []) : [],
    error: status === "error" ? (current?.error ?? null) : null,
    upsert,
    remove,
    reload,
  };
}

export function summarize(items: GearItem[]) {
  let knownGrams = 0;
  let missing = 0;
  let quantity = 0;
  for (const item of items) {
    quantity += item.quantity;
    if (item.weight.effective_g == null) missing += 1;
    else knownGrams += item.weight.effective_g * item.quantity;
  }
  return { knownGrams, missing, quantity };
}
