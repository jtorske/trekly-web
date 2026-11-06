"use client";

import { useEffect, useMemo, useState } from "react";
import PastHikesPicker from "@/components/history/PastHikesPicker";
import QuickAddGear from "@/components/history/QuickAddGear";
import ui from "@/components/ui.module.css";
import { listMyGear, type ProductSummary } from "@/lib/gearApi";
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
  return (
    <>
      <PastHikesPicker catalogue={catalogue} logged={logged} selected={selected} onToggle={onToggle} preferences={preferences} />
      <p className={styles.historyCount} aria-live="polite">
        {selected.size === 0 ? "Nothing picked yet." : selected.size === 1 ? "1 trail picked" : `${selected.size} trails picked`}
      </p>
    </>
  );
}

/** /welcome's "What's in your pack?" step. The flow adds the picks to their gear when they continue. */
export function PackStep({
  selected,
  onToggle,
}: {
  selected: ReadonlyMap<string, ProductSummary>;
  onToggle: (product: ProductSummary) => void;
}) {
  const [owned, setOwned] = useState<Set<string>>(new Set());
  useEffect(() => {
    const controller = new AbortController();
    listMyGear(controller.signal)
      .then((gear) => setOwned(new Set(gear.items.flatMap((item) => (item.product ? [item.product.id] : [])))))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  return (
    <>
      <QuickAddGear owned={owned} selected={selected} onToggle={onToggle} />
      <p className={styles.historyCount} aria-live="polite">
        {selected.size === 0 ? "Nothing picked yet." : selected.size === 1 ? "1 item picked" : `${selected.size} items picked`}
      </p>
    </>
  );
}
