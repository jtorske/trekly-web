"use client";

import { useEffect, useMemo, useState } from "react";
import PastHikesPicker from "@/components/history/PastHikesPicker";
import ui from "@/components/ui.module.css";
import { listHikeLogs } from "@/lib/hikeLogsApi";
import { favouriteParks } from "@/lib/onboarding";
import { useTrailCatalogue } from "@/lib/useTrailCatalogue";
import styles from "./welcome.module.css";

/**
 * /welcome's "Which of these have you hiked?" step. Trails in their home
 * province come first, then the parks they just picked as on their radar.
 * The flow saves the picks as undated hikes when they continue.
 */
export function HikedStep({
  home,
  regions,
  selected,
  onToggle,
}: {
  home: string | null;
  regions: string[];
  selected: ReadonlySet<string>;
  onToggle: (trailId: string) => void;
}) {
  const { catalogue, failed } = useTrailCatalogue();
  const [logged, setLogged] = useState<Set<string> | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    listHikeLogs(controller.signal)
      .then((logs) => setLogged(new Set(logs.map((log) => log.trail.id))))
      .catch(() => setLogged(new Set()));
    return () => controller.abort();
  }, []);
  const preferences = useMemo(
    () => ({ homeProvince: home, favouriteRegions: favouriteParks(regions).map((region) => region.park) }),
    [home, regions],
  );

  if (failed) return <p className={ui.error}>The trail list didn&apos;t load. You can skip this and add past hikes from your journal later.</p>;
  if (!catalogue || !logged) return <div className={`${ui.skeleton} ${styles.historySkeleton}`} aria-label="Loading trails" />;
  // The flow shows how many are picked in its sticky bar, beside Continue.
  return <PastHikesPicker catalogue={catalogue} logged={logged} selected={selected} onToggle={onToggle} preferences={preferences} />;
}
