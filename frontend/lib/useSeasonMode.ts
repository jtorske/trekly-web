"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { useAuth } from "@/components/AuthProvider";
import { getPreferences, onPreferencesUpdated, updatePreferences } from "./preferencesApi";
import {
  SEASON_MODE_STORAGE_KEY,
  choiceToStore,
  readStoredMode,
  resolveSeasonMode,
  writeStoredMode,
  type SeasonInfo,
} from "./seasonMode";
import type { SeasonMode } from "./trailsApi";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// One request per page load: the answer changes at most daily.
let seasonRequest: Promise<SeasonInfo | null> | null = null;

/** The current season from GET /api/season (app/season.py); null if the API can't be reached. */
export function fetchSeason(): Promise<SeasonInfo | null> {
  seasonRequest ??= fetch(`${API_BASE}/api/season`)
    .then((res) => (res.ok ? (res.json() as Promise<SeasonInfo>) : null))
    .catch(() => null)
    .then((info) => {
      if (!info) seasonRequest = null; // try again next time
      return info;
    });
  return seasonRequest;
}

// The browser's stored choice (signed-out visitors), kept in step across tabs.
const LOCAL_EVENT = "trekly:season-mode";

function subscribeLocal(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === SEASON_MODE_STORAGE_KEY) onChange();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(LOCAL_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(LOCAL_EVENT, onChange);
  };
}

const localSnapshot = () => readStoredMode(globalThis.localStorage);
const serverSnapshot = () => null;

/**
 * Explore's Summer / Winter mode: the person's own choice if they made one
 * (their preferences when signed in, this browser when not), else the current
 * season. `mode` is null until the season has loaded.
 */
export function useSeasonMode(): {
  mode: SeasonMode | null;
  season: SeasonMode | null;
  setMode: (mode: SeasonMode) => void;
} {
  const { status } = useAuth();
  const [season, setSeason] = useState<SeasonMode | null>(null);
  // Signed in: their preferences (undefined until loaded).
  const [savedPref, setSavedPref] = useState<SeasonMode | null | undefined>(undefined);
  const savedLocal = useSyncExternalStore(subscribeLocal, localSnapshot, serverSnapshot);

  useEffect(() => {
    let live = true;
    void fetchSeason().then((info) => {
      // Without the API, fall back to summer: it hides nothing a hiker needs.
      if (live) setSeason(info?.season ?? "summer");
    });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (status !== "signedIn") return;
    const controller = new AbortController();
    getPreferences(controller.signal)
      .then((prefs) => setSavedPref(prefs.season_mode ?? null))
      .catch(() => {
        // Unreadable: fall back to this browser's choice.
      });
    const stop = onPreferencesUpdated((prefs) => setSavedPref(prefs.season_mode ?? null));
    return () => {
      controller.abort();
      stop();
    };
  }, [status]);

  const saved = status === "signedIn" && savedPref !== undefined ? savedPref : savedLocal;

  const setMode = useCallback(
    (chosen: SeasonMode) => {
      const store = choiceToStore(chosen, season);
      // This browser always keeps it too, so the toggle answers at once.
      writeStoredMode(globalThis.localStorage, store);
      window.dispatchEvent(new Event(LOCAL_EVENT));
      if (status === "signedIn") {
        setSavedPref(store);
        void updatePreferences({ season_mode: store }).catch(() => {
          // Still applied for this visit; it just isn't remembered across devices.
        });
      }
    },
    [season, status],
  );

  return { mode: resolveSeasonMode(saved, season), season, setMode };
}
