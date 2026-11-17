"use client";

import { useEffect, useState } from "react";
import { CATALOGUE_SIZE } from "./journal";
import { searchTrails, type TrailListItem } from "./trailsApi";

// One copy per page load: the catalogue barely changes, and fetching it again
// on every Journal tab open cost 0.3-2 s against the hosted API.
let loaded: TrailListItem[] | null = null;
let inflight: Promise<TrailListItem[]> | null = null;

/** Starts loading the catalogue (once), so a Journal tab opened later already has it. */
export function preloadTrailCatalogue(): Promise<TrailListItem[]> {
  if (loaded) return Promise.resolve(loaded);
  inflight ??= searchTrails("", undefined, { limit: CATALOGUE_SIZE }).then(
    (trails) => {
      loaded = trails;
      return trails;
    },
    (error: unknown) => {
      inflight = null; // the next caller tries again
      throw error;
    },
  );
  return inflight;
}

/**
 * The trail catalogue the Trail Journal is laid out against, shared by the
 * journal and the profile's Journal tab so their counts agree. Loads only
 * while `enabled`.
 */
export function useTrailCatalogue(enabled = true) {
  const [catalogue, setCatalogue] = useState<TrailListItem[] | null>(loaded);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!enabled || catalogue) return;
    let live = true;
    preloadTrailCatalogue().then(
      (trails) => {
        if (live) setCatalogue(trails);
      },
      () => {
        if (live) setFailed(true);
      },
    );
    return () => {
      live = false;
    };
  }, [enabled, catalogue]);

  return { catalogue, failed };
}
