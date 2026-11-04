"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { favouriteParks } from "./onboarding";
import { getPreferences, onPreferencesUpdated } from "./preferencesApi";

type Parks = { park: string; label: string }[];

/**
 * The signed-in person's favourite regions as Explore parks. `null` while
 * loading (so Explore can wait before pre-picking them); [] for guests or
 * when nothing was picked.
 */
export function useFavouriteParks(): Parks | null {
  const { status, user } = useAuth();
  const userId = user?.id ?? null;
  const [state, setState] = useState<{ userId: string; parks: Parks } | null>(null);

  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    getPreferences(controller.signal)
      .then((prefs) => setState({ userId, parks: favouriteParks(prefs.favourite_regions) }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setState({ userId, parks: [] });
      });
    return () => controller.abort();
  }, [userId]);

  useEffect(
    () =>
      onPreferencesUpdated((prefs) => {
        if (userId) setState({ userId, parks: favouriteParks(prefs.favourite_regions) });
      }),
    [userId],
  );

  if (status === "loading") return null;
  if (!userId) return [];
  return state?.userId === userId ? state.parks : null;
}
