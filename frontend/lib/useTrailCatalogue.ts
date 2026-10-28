"use client";

import { useEffect, useState } from "react";
import { CATALOGUE_SIZE } from "./journal";
import { searchTrails, type TrailListItem } from "./trailsApi";

/**
 * The trail catalogue the Trail Journal is laid out against, shared by the
 * journal and the profile's Journal tab so their counts agree. Loads only
 * while `enabled`.
 */
export function useTrailCatalogue(enabled = true) {
  const [catalogue, setCatalogue] = useState<TrailListItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    searchTrails("", controller.signal, { limit: CATALOGUE_SIZE })
      .then(setCatalogue)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [enabled]);

  return { catalogue, failed };
}
