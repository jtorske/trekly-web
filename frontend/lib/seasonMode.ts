/**
 * Explore's Summer / Winter mode. The season itself comes from the API
 * (GET /api/season, backend app/season.py), the only place the dates and the
 * snow rule live; this file only decides between that and the person's own
 * choice, and remembers the choice.
 */
import type { SeasonMode } from "./trailsApi.ts";

export interface SeasonInfo {
  season: SeasonMode;
  by_date: SeasonMode;
  adjusted_by_snow: boolean;
  next_change: string;
  today: string;
}

/** Signed-out visitors' choice, per browser (signed-in people keep theirs in preferences). */
export const SEASON_MODE_STORAGE_KEY = "trekly.season-mode";

/** The mode to show: their own choice if they made one, else the current season. */
export function resolveSeasonMode(saved: SeasonMode | null | undefined, season: SeasonMode | null): SeasonMode | null {
  return saved ?? season;
}

/**
 * What to store when they pick `chosen`: picking the current season stores
 * nothing (null), so the toggle follows the season again when it changes.
 */
export function choiceToStore(chosen: SeasonMode, season: SeasonMode | null): SeasonMode | null {
  return season !== null && chosen === season ? null : chosen;
}

export function parseStoredMode(value: string | null | undefined): SeasonMode | null {
  return value === "summer" || value === "winter" ? value : null;
}

export function readStoredMode(storage: Pick<Storage, "getItem"> | undefined): SeasonMode | null {
  try {
    return parseStoredMode(storage?.getItem(SEASON_MODE_STORAGE_KEY));
  } catch {
    return null; // private mode, blocked storage
  }
}

export function writeStoredMode(storage: Pick<Storage, "setItem" | "removeItem"> | undefined, mode: SeasonMode | null) {
  try {
    if (mode) storage?.setItem(SEASON_MODE_STORAGE_KEY, mode);
    else storage?.removeItem(SEASON_MODE_STORAGE_KEY);
  } catch {
    // Storage can be unavailable; the toggle still works for this visit.
  }
}
