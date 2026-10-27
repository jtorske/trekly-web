"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { getProfile, type Profile } from "./accountApi";

export const PROFILE_EVENT = "trekly:profile-updated";

/** Tell every mounted useProfile() (e.g. the navbar avatar) about a change. */
export function announceProfile(profile: Profile) {
  window.dispatchEvent(new CustomEvent<Profile>(PROFILE_EVENT, { detail: profile }));
}

export function useProfile() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [state, setState] = useState<{ userId: string; profile: Profile | null; error: string | null } | null>(null);
  const [token, setToken] = useState(0);

  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    getProfile(controller.signal)
      .then((profile) => setState({ userId, profile, error: null }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setState({ userId, profile: null, error: error instanceof Error ? error.message : "Couldn't load your profile." });
      });
    return () => controller.abort();
  }, [userId, token]);

  useEffect(() => {
    const onUpdate = (event: Event) => {
      const profile = (event as CustomEvent<Profile>).detail;
      if (profile.id === userId) setState({ userId: profile.id, profile, error: null });
    };
    window.addEventListener(PROFILE_EVENT, onUpdate);
    return () => window.removeEventListener(PROFILE_EVENT, onUpdate);
  }, [userId]);

  const current = state && state.userId === userId ? state : null;
  return {
    profile: current?.profile ?? null,
    error: current?.error ?? null,
    loading: Boolean(userId) && !current,
    reload: useCallback(() => setToken((t) => t + 1), []),
  };
}
