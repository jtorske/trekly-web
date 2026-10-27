"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useAuth } from "@/components/AuthProvider";
import { getProfile, updateProfile, type Profile } from "./accountApi";
import { announceProfile, PROFILE_EVENT } from "./useProfile";
import { DEFAULT_UNITS, isUnitSystem, legacyUnitsToMigrate, resolveUnits, type UnitSystem } from "./units";

// The per-browser setting from before units were an account setting.
const LEGACY_KEY = "trekly:units";
// Last known setting for this browser's account, so imperial users don't see
// a flash of metric while the profile loads. A convenience only: the
// profile is the source of truth.
const CACHE_KEY = "trekly:units-cache";

type Saved = { userId: string; units: UnitSystem | null };

const listeners = new Set<() => void>();
let saved: Saved | null = null;
let loading: string | null = null;

function storageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string | null) {
  try {
    if (value == null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Unavailable (private mode): the in-memory value still applies.
  }
}

function cached(userId: string): UnitSystem | null {
  try {
    const value = JSON.parse(storageGet(CACHE_KEY) ?? "null") as Saved | null;
    return value?.userId === userId && isUnitSystem(value.units) ? value.units : null;
  } catch {
    return null;
  }
}

function publish(next: Saved) {
  saved = next;
  storageSet(CACHE_KEY, JSON.stringify(next));
  listeners.forEach((listener) => listener());
}

async function load(userId: string) {
  if (loading === userId) return;
  loading = userId;
  try {
    let profile: Profile = await getProfile();
    const legacy = legacyUnitsToMigrate(profile.units, storageGet(LEGACY_KEY));
    if (legacy) {
      // Keep the choice they made before this was an account setting.
      profile = await updateProfile({ units: legacy });
      announceProfile(profile);
    }
    storageSet(LEGACY_KEY, null);
    if (profile.id === userId) publish({ userId, units: profile.units });
  } catch {
    // Offline or signed out mid-request: show the default (or cached) units.
  } finally {
    if (loading === userId) loading = null;
  }
}

// Any profile save (Settings, or another tab of the app) carries the units.
function onProfile(event: Event) {
  const profile = (event as CustomEvent<Profile>).detail;
  if (saved?.userId !== profile.id || saved.units !== profile.units) publish({ userId: profile.id, units: profile.units });
}

function subscribe(listener: () => void) {
  if (listeners.size === 0) window.addEventListener(PROFILE_EVENT, onProfile);
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener(PROFILE_EVENT, onProfile);
  };
}

/**
 * The account's display units: metric unless the user chose imperial in
 * Settings. Guests always get metric. Canonical data is always metric; pass
 * the result to lib/units formatters.
 */
export function useUnits(): [UnitSystem, (next: UnitSystem) => Promise<void>] {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const units = useSyncExternalStore(
    subscribe,
    () => {
      if (!userId) return DEFAULT_UNITS;
      return resolveUnits(true, saved?.userId === userId ? saved.units : cached(userId));
    },
    () => DEFAULT_UNITS,
  );

  useEffect(() => {
    if (userId && saved?.userId !== userId) void load(userId);
  }, [userId]);

  const set = useCallback(
    async (next: UnitSystem) => {
      if (!userId) return;
      const previous = saved?.userId === userId ? saved.units : null;
      publish({ userId, units: next });
      try {
        announceProfile(await updateProfile({ units: next }));
      } catch (error) {
        publish({ userId, units: previous });
        throw error;
      }
    },
    [userId],
  );
  return [units, set];
}
