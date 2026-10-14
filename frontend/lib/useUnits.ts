"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { UnitSystem } from "./units";

const KEY = "trekly:units";
const listeners = new Set<() => void>();
// Used when localStorage is unavailable (private mode), so the choice still
// applies for the rest of this visit.
let memory: UnitSystem = "imperial";

function read(): UnitSystem {
  try {
    const stored = window.localStorage.getItem(KEY);
    return stored === "metric" || stored === "imperial" ? stored : memory;
  } catch {
    return memory;
  }
}

/** Per-browser display preference; canonical data is always metric. */
export function useUnits(): [UnitSystem, (next: UnitSystem) => void] {
  const units = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    read,
    () => "imperial" as UnitSystem,
  );
  const set = useCallback((next: UnitSystem) => {
    memory = next;
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // Not persisted; `memory` keeps it for this visit.
    }
    listeners.forEach((listener) => listener());
  }, []);
  return [units, set];
}
