"use client";

import { Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import SaveTrailButton from "@/components/SaveTrailButton";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { TERRAIN_LABELS, type Terrain } from "@/app/packplanner/packingList";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import { metersToFeet } from "@/lib/units";
import styles from "./page.module.css";

const TERRAINS = Object.keys(TERRAIN_LABELS) as Terrain[];
const RESULT_LIMIT = 100;

function isTerrain(value: string | null): value is Terrain {
  return value !== null && (TERRAINS as string[]).includes(value);
}

function TrailCard({
  trail,
  saved,
  pending,
  onToggleSave,
  returnTo,
}: {
  trail: TrailListItem;
  saved: boolean;
  pending: boolean;
  onToggleSave: (trailId: string, makeSaved: boolean) => Promise<void>;
  returnTo: string;
}) {
  return (
    <li className={styles.cardItem}>
      <Link
        href={`/trails?id=${encodeURIComponent(trail.id)}`}
        className={styles.card}
      >
        <div className={styles.cardMain}>
          <h2 className={styles.cardName}>{trail.name}</h2>
          <p className={styles.cardRegion}>{trail.region}</p>
        </div>

        <div className={styles.cardMeta}>
          <span className={`${styles.terrainTag} ${styles[trail.terrain]}`}>
            {TERRAIN_LABELS[trail.terrain]}
          </span>
          {trail.typical_duration_nights != null && (
            <span className={styles.metaItem}>
              {trail.typical_duration_nights}{" "}
              {trail.typical_duration_nights === 1 ? "night" : "nights"}
            </span>
          )}
          {trail.elevation_gain_m != null && (
            <span className={styles.metaItem}>
              {metersToFeet(trail.elevation_gain_m).toLocaleString()} ft gain
            </span>
          )}
        </div>
      </Link>
      <div className={styles.cardSave}>
        <SaveTrailButton
          trailId={trail.id}
          trailName={trail.name}
          saved={saved}
          pending={pending}
          onToggle={onToggleSave}
          returnTo={returnTo}
          compact
        />
      </div>
    </li>
  );
}

function ExploreContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const q = searchParams.get("q")?.trim() ?? "";
  const terrainParam = searchParams.get("terrain");
  const terrain = isTerrain(terrainParam) ? terrainParam : undefined;

  const [input, setInput] = useState(q);
  const savedTrails = useSavedTrails();
  const { status: authStatus } = useAuth();
  const resumedSave = useRef(false);
  const saveParam = searchParams.get("save");
  const returnTo = `/trail-list${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const [result, setResult] = useState<{
    key: string;
    trails: TrailListItem[] | null;
  } | null>(null);

  const requestKey = `${q}|${terrain ?? ""}`;

  const updateUrl = useCallback(
    (nextQuery: string, nextTerrain: Terrain | undefined) => {
      const params = new URLSearchParams();
      if (nextQuery) params.set("q", nextQuery);
      if (nextTerrain) params.set("terrain", nextTerrain);
      const search = params.toString();
      router.replace(search ? `/trail-list?${search}` : "/trail-list", {
        scroll: false,
      });
    },
    [router],
  );

  // Typing updates the URL (debounced); the URL is what drives the fetch, so
  // links from the landing page and shared URLs behave the same as typing.
  useEffect(() => {
    const trimmed = input.trim();
    if (trimmed === q) return;
    const timer = window.setTimeout(() => updateUrl(trimmed, terrain), 300);
    return () => window.clearTimeout(timer);
  }, [input, q, terrain, updateUrl]);

  useEffect(() => {
    const controller = new AbortController();
    searchTrails(q, controller.signal, { terrain, limit: RESULT_LIMIT })
      .then((trails) => setResult({ key: requestKey, trails }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setResult({ key: requestKey, trails: null });
        }
      });
    return () => controller.abort();
  }, [q, terrain, requestKey]);

  // Back from sign-in after a guest clicked Save on a card: finish that save.
  useEffect(() => {
    if (!saveParam || authStatus !== "signedIn" || savedTrails.loading || resumedSave.current) return;
    resumedSave.current = true;
    const done = () => updateUrl(q, terrain);
    if (savedTrails.savedIds.has(saveParam)) done();
    else savedTrails.toggle(saveParam, true).catch(() => undefined).finally(done);
  }, [saveParam, authStatus, savedTrails, updateUrl, q, terrain]);

  const isLoading = result?.key !== requestKey;
  const trails = result?.trails;
  const failed = !isLoading && trails === null;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    updateUrl(input.trim(), terrain);
  };

  return (
    <main className={styles.page}>
      <div className={styles.texture} aria-hidden="true" />

      <div className={styles.intro}>
        <h1 className={styles.title}>Explore</h1>
        <p className={styles.subtitle}>
          Search backpacking trails by name or region, then open one to see
          conditions and plan your pack.
        </p>
      </div>

      <div className={styles.controls}>
        <form className={styles.searchBar} onSubmit={handleSubmit} role="search">
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search trails or regions…"
            aria-label="Search trails or regions"
            autoComplete="off"
            value={input}
            onChange={(event) => setInput(event.target.value)}
          />
          <button className={styles.searchButton} type="submit">
            Search
          </button>
        </form>

        <div className={styles.filters} role="group" aria-label="Filter by difficulty">
          <button
            type="button"
            className={styles.chip}
            aria-pressed={!terrain}
            onClick={() => updateUrl(input.trim(), undefined)}
          >
            All
          </button>
          {TERRAINS.map((option) => (
            <button
              key={option}
              type="button"
              className={styles.chip}
              aria-pressed={terrain === option}
              onClick={() => updateUrl(input.trim(), option)}
            >
              {TERRAIN_LABELS[option]}
            </button>
          ))}
        </div>
      </div>

      <section className={styles.results} aria-live="polite" aria-busy={isLoading}>
        {failed ? (
          <p className={styles.status}>
            We couldn&apos;t load trails right now. Check that the trail service
            is running and try again.
          </p>
        ) : !trails ? (
          <p className={styles.status}>Loading trails…</p>
        ) : trails.length === 0 ? (
          <p className={styles.status}>
            No trails match
            {q ? <> &ldquo;{q}&rdquo;</> : null}
            {terrain ? <> at {TERRAIN_LABELS[terrain].toLowerCase()} difficulty</> : null}
            . Try a broader search.
          </p>
        ) : (
          <>
            <p className={styles.count}>
              {trails.length === RESULT_LIMIT ? `${RESULT_LIMIT}+` : trails.length}{" "}
              {trails.length === 1 ? "trail" : "trails"}
              {q ? <> matching &ldquo;{q}&rdquo;</> : null}
            </p>
            <ul className={`${styles.list} ${isLoading ? styles.stale : ""}`}>
              {trails.map((trail) => (
                <TrailCard
                  key={trail.id}
                  trail={trail}
                  saved={savedTrails.savedIds.has(trail.id)}
                  pending={savedTrails.pending.has(trail.id)}
                  onToggleSave={savedTrails.toggle}
                  returnTo={returnTo}
                />
              ))}
            </ul>
          </>
        )}
      </section>
    </main>
  );
}

export default function ExplorePage() {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <ExploreContent />
    </Suspense>
  );
}
