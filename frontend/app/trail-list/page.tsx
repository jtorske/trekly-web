"use client";

import { Suspense, useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import SaveTrailButton from "@/components/SaveTrailButton";
import ui from "@/components/ui.module.css";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { TERRAIN_LABELS, type Terrain } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import { TRAIL_SORT_LABELS, isTrailSort, sortTrails, trailTitles, type TrailSort } from "@/lib/trailOrder";
import { searchTrails, type TrailListItem, type TripType } from "@/lib/trailsApi";
import { formatTrailDistance, formatTrailElevation, type UnitSystem } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import styles from "./page.module.css";

const TERRAINS = Object.keys(TERRAIN_LABELS) as Terrain[];
const RESULT_LIMIT = 100;

const TRIP_LABELS: Record<TripType, string> = {
  overnight: "Backpacking",
  day: "Day hikes",
};
const TRIPS = Object.keys(TRIP_LABELS) as TripType[];
const SORTS = Object.keys(TRAIL_SORT_LABELS) as TrailSort[];

function isTerrain(value: string | null): value is Terrain {
  return value !== null && (TERRAINS as string[]).includes(value);
}

function isTrip(value: string | null): value is TripType {
  return value !== null && (TRIPS as string[]).includes(value);
}

interface Filters {
  terrain?: Terrain;
  trip?: TripType;
  /** Not counted as a filter; kept in the URL like one. */
  sort?: TrailSort;
}

function FilterGroup<T extends string>({
  label,
  options,
  labels,
  value,
  onChange,
}: {
  label: string;
  options: T[];
  labels: Record<T, string>;
  value: T | undefined;
  onChange: (value: T | undefined) => void;
}) {
  return (
    <fieldset className={styles.filterGroup}>
      <legend className={styles.filterLegend}>{label}</legend>
      <div className={styles.filterChips}>
        <button type="button" className={styles.chip} aria-pressed={!value} onClick={() => onChange(undefined)}>
          All
        </button>
        {options.map((option) => (
          <button
            key={option}
            type="button"
            className={styles.chip}
            aria-pressed={value === option}
            onClick={() => onChange(option)}
          >
            {labels[option]}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function TrailCard({
  trail,
  title,
  saved,
  pending,
  onToggleSave,
  returnTo,
  units,
}: {
  trail: TrailListItem;
  title: string;
  saved: boolean;
  pending: boolean;
  onToggleSave: (trailId: string, makeSaved: boolean) => Promise<void>;
  returnTo: string;
  units: UnitSystem;
}) {
  const distance = formatTrailDistance(trail.distance_km, trail.route_type, units);
  const gain = formatTrailElevation(trail.elevation_gain_m, units);
  return (
    <li className={styles.cardItem}>
      <Link
        href={`/trails?id=${encodeURIComponent(trail.id)}`}
        className={styles.card}
      >
        <div className={styles.cardMain}>
          <h2 className={styles.cardName}>{title}</h2>
          <p className={styles.cardRegion}>{trail.region}</p>
        </div>

        <div className={styles.cardMeta}>
          <span className={`${styles.terrainTag} ${styles[trail.terrain]}`}>
            {TERRAIN_LABELS[trail.terrain]}
          </span>
          {trail.typical_duration_nights != null && (
            <span className={styles.metaItem}>
              {tripLengthLabel(trail.typical_duration_nights)}
            </span>
          )}
          {distance && <span className={styles.metaItem}>{distance}</span>}
          {gain && <span className={styles.metaItem}>{gain} gain</span>}
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
  const tripParam = searchParams.get("trip");
  const trip = isTrip(tripParam) ? tripParam : undefined;
  const sortParam = searchParams.get("sort");
  const sort: TrailSort = isTrailSort(sortParam) ? sortParam : "popular";
  const filters: Filters = { terrain, trip, sort };
  const activeFilters = (terrain ? 1 : 0) + (trip ? 1 : 0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();

  const [input, setInput] = useState(q);
  const savedTrails = useSavedTrails();
  const [units] = useUnits();
  const { status: authStatus } = useAuth();
  const resumedSave = useRef(false);
  const saveParam = searchParams.get("save");
  const returnTo = `/trail-list${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const [result, setResult] = useState<{
    key: string;
    trails: TrailListItem[] | null;
  } | null>(null);
  // Bumped by "Try again" so the same search is fetched afresh.
  const [attempt, setAttempt] = useState(0);

  const requestKey = `${q}|${terrain ?? ""}|${trip ?? ""}|${attempt}`;

  const updateUrl = useCallback(
    (nextQuery: string, next: Filters) => {
      const params = new URLSearchParams();
      if (nextQuery) params.set("q", nextQuery);
      if (next.trip) params.set("trip", next.trip);
      if (next.terrain) params.set("terrain", next.terrain);
      if (next.sort && next.sort !== "popular") params.set("sort", next.sort);
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
    const timer = window.setTimeout(() => updateUrl(trimmed, { terrain, trip, sort }), 300);
    return () => window.clearTimeout(timer);
  }, [input, q, terrain, trip, sort, updateUrl]);

  useEffect(() => {
    const controller = new AbortController();
    searchTrails(q, controller.signal, { terrain, trip, limit: RESULT_LIMIT })
      .then((trails) => setResult({ key: requestKey, trails }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setResult({ key: requestKey, trails: null });
        }
      });
    return () => controller.abort();
  }, [q, terrain, trip, attempt, requestKey]);

  // Back from sign-in after a guest clicked Save on a card: finish that save.
  useEffect(() => {
    if (!saveParam || authStatus !== "signedIn" || savedTrails.loading || resumedSave.current) return;
    resumedSave.current = true;
    const done = () => updateUrl(q, { terrain, trip, sort });
    if (savedTrails.savedIds.has(saveParam)) done();
    else savedTrails.toggle(saveParam, true).catch(() => undefined).finally(done);
  }, [saveParam, authStatus, savedTrails, updateUrl, q, terrain, trip, sort]);

  const isLoading = result?.key !== requestKey;
  const trails = result?.trails;
  const failed = !isLoading && trails === null;
  const sorted = trails ? sortTrails(trails, sort) : null;
  const titles = trailTitles(trails ?? []);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    updateUrl(input.trim(), filters);
  };

  const setFilter = (next: Filters) => updateUrl(input.trim(), next);

  return (
    <main className={styles.page}>

      <h1 className={ui.srOnly}>Explore trails</h1>

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
          <button
            type="button"
            className={styles.filterButton}
            aria-expanded={filtersOpen}
            aria-controls={filtersId}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <svg viewBox="0 0 20 20" aria-hidden="true" className={styles.filterIcon}>
              <path d="M3 5h14M6 10h8M9 15h2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            <span className={styles.filterLabel}>Filters</span>
            {activeFilters > 0 && (
              <span className={styles.filterCount}>
                {activeFilters}
                <span className={ui.srOnly}> active</span>
              </span>
            )}
          </button>
          <button className={styles.searchButton} type="submit">
            Search
          </button>
        </form>

        {filtersOpen && (
          <div
            id={filtersId}
            className={styles.filterPanel}
            onKeyDown={(event) => {
              if (event.key === "Escape") setFiltersOpen(false);
            }}
          >
            <FilterGroup
              label="Trip type"
              options={TRIPS}
              labels={TRIP_LABELS}
              value={trip}
              onChange={(value) => setFilter({ ...filters, trip: value })}
            />
            <FilterGroup
              label="Difficulty"
              options={TERRAINS}
              labels={TERRAIN_LABELS}
              value={terrain}
              onChange={(value) => setFilter({ ...filters, terrain: value })}
            />
            <div className={styles.filterFooter}>
              {activeFilters > 0 && (
                <button type="button" className={ui.ghost} onClick={() => setFilter({ sort })}>
                  Clear filters
                </button>
              )}
              <button type="button" className={ui.secondary} onClick={() => setFiltersOpen(false)}>
                Done
              </button>
            </div>
          </div>
        )}

        {!filtersOpen && activeFilters > 0 && (
          <ul className={styles.activeFilters} aria-label="Active filters">
            {trip && (
              <li>
                <button
                  type="button"
                  className={styles.activeChip}
                  onClick={() => setFilter({ ...filters, trip: undefined })}
                  aria-label={`Remove filter: ${TRIP_LABELS[trip]}`}
                >
                  {TRIP_LABELS[trip]} <span aria-hidden="true">×</span>
                </button>
              </li>
            )}
            {terrain && (
              <li>
                <button
                  type="button"
                  className={styles.activeChip}
                  onClick={() => setFilter({ ...filters, terrain: undefined })}
                  aria-label={`Remove filter: ${TERRAIN_LABELS[terrain]}`}
                >
                  {TERRAIN_LABELS[terrain]} <span aria-hidden="true">×</span>
                </button>
              </li>
            )}
          </ul>
        )}
      </div>

      <section className={styles.results} aria-live="polite" aria-busy={isLoading}>
        {failed ? (
          <div className={styles.status} role="alert">
            <p>We couldn&apos;t load trails. Check your connection and try again.</p>
            <button type="button" className={`${ui.secondary} ${styles.retry}`} onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </div>
        ) : !sorted ? (
          <p className={styles.status}>Loading trails…</p>
        ) : sorted.length === 0 ? (
          <p className={styles.status}>
            No trails match
            {q ? <> &ldquo;{q}&rdquo;</> : null}
            {trip ? <> among {TRIP_LABELS[trip].toLowerCase()} trips</> : null}
            {terrain ? <> at {TERRAIN_LABELS[terrain].toLowerCase()} difficulty</> : null}
            . Try a broader search or clear a filter.
          </p>
        ) : (
          <>
            <div className={styles.resultsHead}>
              {/* The API caps the catalogue at RESULT_LIMIT, so this count is exact. */}
              <p className={styles.count}>
                {sorted.length}{" "}
                {trip === "overnight" ? "backpacking " : trip === "day" ? "day-hike " : ""}
                {sorted.length === 1 ? "trail" : "trails"}
                {q ? <> matching &ldquo;{q}&rdquo;</> : null}
              </p>
              <label className={styles.sort}>
                <span className={styles.sortLabel}>Sort</span>
                <select
                  className={ui.input}
                  value={sort}
                  onChange={(event) => setFilter({ ...filters, sort: event.target.value as TrailSort })}
                >
                  {SORTS.map((option) => (
                    <option key={option} value={option}>
                      {TRAIL_SORT_LABELS[option]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <ul className={`${styles.list} ${isLoading ? styles.stale : ""}`}>
              {sorted.map((trail) => (
                <TrailCard
                  key={trail.id}
                  trail={trail}
                  title={titles.get(trail.id) ?? trail.name}
                  saved={savedTrails.savedIds.has(trail.id)}
                  pending={savedTrails.pending.has(trail.id)}
                  onToggleSave={savedTrails.toggle}
                  returnTo={returnTo}
                  units={units}
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
