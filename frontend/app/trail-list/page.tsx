"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import {
  PARK_TYPE_LABELS,
  PROVINCE_NAMES,
  QUICK_PARKS,
  TRIP_LABELS,
  WITHIN_OPTIONS,
  activeFilterCount,
  clearFilters,
  exploreSearch,
  formatMapView,
  keepViewParams,
  parseExploreParams,
  parseExploreView,
  parseMapView,
  provinceOrder,
  toggle,
  toggleTrip,
  withProvinces,
  withViewParam,
  withinKm,
  withinLabel,
  withoutNear,
  type Bounds,
  type ExploreFilters,
  type ExploreView,
  type MapView,
} from "@/lib/exploreFilters";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { TERRAIN_LABELS, type Terrain } from "@/lib/terrain";
import { TRAIL_SORT_LABELS, sortTrails, trailTitles, type TrailSort } from "@/lib/trailOrder";
import {
  searchExplore,
  type ParkTypeFilter,
  type TrailFacets,
  type TrailSearchItem,
  type TrailSearchRequest,
  type TripType,
} from "@/lib/trailsApi";
import type { UnitSystem } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import TrailCard, { TrailCardSkeleton } from "./TrailCard";
import styles from "./page.module.css";

// MapLibre is big and needs the browser: load it only when a map is on screen.
const ExploreMap = dynamic(() => import("./ExploreMap"), {
  ssr: false,
  loading: () => (
    <div className={`${styles.mapPlaceholder} ${styles.mapLoading}`} aria-hidden="true">
      <span>Loading map…</span>
    </div>
  ),
});

const TERRAINS = Object.keys(TERRAIN_LABELS) as Terrain[];
const RESULT_LIMIT = 100;
const TRIPS = Object.keys(TRIP_LABELS) as TripType[];
const PARK_TYPES = Object.keys(PARK_TYPE_LABELS) as ParkTypeFilter[];
const MOBILE_QUERY = "(max-width: 640px)";
/** The list and the map side by side; narrower screens toggle between them. */
const SPLIT_QUERY = "(min-width: 1100px)";
const SKELETON_CARDS = 6;

function subscribeSplit(onChange: () => void) {
  const query = window.matchMedia(SPLIT_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
const isSplit = () => window.matchMedia(SPLIT_QUERY).matches;

function provinceName(code: string): string {
  return PROVINCE_NAMES[code] ?? code;
}

/** Lower-case, accents stripped: "gaspesie" finds "Gaspésie". */
function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
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

/** Multi-select chips with counts. An option with no matches is greyed out
 * (and can't be picked) unless it's already selected. */
function CountChipGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: { value: string; label: string; count: number | null }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <fieldset className={styles.filterGroup}>
      <legend className={styles.filterLegend}>{label}</legend>
      <div className={styles.filterChips}>
        {options.map((option) => {
          const on = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              className={styles.chip}
              aria-pressed={on}
              disabled={!on && option.count === 0}
              onClick={() => onToggle(option.value)}
            >
              {option.label}
              {option.count !== null && <span className={styles.chipCount}>{option.count}</span>}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function ParkPicker({
  parks,
  selected,
  provinces,
  onToggle,
}: {
  parks: TrailFacets["parks"];
  selected: string[];
  provinces: string[];
  onToggle: (park: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const listId = useId();
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  // Narrowed to the picked provinces; picked parks always stay visible.
  const inProvinces = parks.filter(
    (park) =>
      selected.includes(park.name) ||
      !provinces.length ||
      park.province_codes.some((code) => provinces.includes(code)),
  );
  const needle = fold(query.trim());
  const shown = needle ? inProvinces.filter((park) => fold(park.name).includes(needle)) : inProvinces;
  const summary =
    selected.length === 0 ? "Any park" : selected.length === 1 ? selected[0] : `${selected.length} parks`;

  return (
    <fieldset className={styles.filterGroup}>
      <legend className={styles.filterLegend}>Park</legend>
      <button
        type="button"
        className={styles.pickerButton}
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className={styles.pickerSummary}>{summary}</span>
        <svg viewBox="0 0 20 20" aria-hidden="true" className={styles.pickerChevron}>
          <path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div id={listId} className={styles.picker}>
          <input
            ref={searchRef}
            className={`${ui.input} ${styles.pickerSearch}`}
            type="search"
            placeholder={provinces.length ? `Search parks in ${provinces.map(provinceName).join(", ")}` : "Search parks"}
            aria-label="Search parks"
            autoComplete="off"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {shown.length === 0 ? (
            <p className={styles.pickerEmpty}>No parks match &ldquo;{query.trim()}&rdquo;.</p>
          ) : (
            <ul className={styles.pickerList}>
              {shown.map((park) => {
                const on = selected.includes(park.name);
                const disabled = !on && park.count === 0;
                return (
                  <li key={park.name}>
                    <label className={`${styles.pickerOption} ${disabled ? styles.pickerOptionOff : ""}`}>
                      <input type="checkbox" checked={on} disabled={disabled} onChange={() => onToggle(park.name)} />
                      <span className={styles.pickerName}>{park.name}</span>
                      <span className={styles.pickerMeta}>
                        {park.province_codes.join(", ")} · {park.count}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </fieldset>
  );
}

/** "stopped": turned off here, so a lingering near=1 mustn't re-ask. */
type GeoStatus = "idle" | "locating" | "on" | "denied" | "unavailable" | "stopped";

function NearMe({
  filters,
  status,
  units,
  onLocate,
  onStop,
  onWithin,
}: {
  filters: ExploreFilters;
  status: GeoStatus;
  units: UnitSystem;
  onLocate: () => void;
  onStop: () => void;
  onWithin: (value: number | undefined) => void;
}) {
  const unit = units === "imperial" ? "mi" : "km";
  const within = filters.within;
  return (
    <fieldset className={styles.filterGroup}>
      <legend className={styles.filterLegend}>Near me</legend>
      {filters.near && status === "on" ? (
        <>
          <div className={styles.filterChips}>
            <button type="button" className={styles.chip} aria-pressed={!within} onClick={() => onWithin(undefined)}>
              Any distance
            </button>
            {WITHIN_OPTIONS.map((value) => (
              <button
                key={value}
                type="button"
                className={styles.chip}
                aria-pressed={within?.value === value && within.unit === unit}
                onClick={() => onWithin(value)}
              >
                {value} {unit}
              </button>
            ))}
          </div>
          <button type="button" className={styles.textButton} onClick={onStop}>
            Stop using my location
          </button>
        </>
      ) : (
        <>
          <button type="button" className={styles.locateButton} onClick={onLocate} disabled={status === "locating"}>
            <svg viewBox="0 0 20 20" aria-hidden="true" className={styles.filterIcon}>
              <circle cx="10" cy="10" r="3" fill="currentColor" />
              <path
                d="M10 2.5v2.5M10 15v2.5M2.5 10H5M15 10h2.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
              <circle cx="10" cy="10" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
            </svg>
            {status === "locating" ? "Finding you…" : "Use my location"}
          </button>
          {status === "denied" && (
            <p className={styles.geoMessage} role="status">
              Location access is blocked. Allow it for Trekly in your browser to search near you.
            </p>
          )}
          {status === "unavailable" && (
            <p className={styles.geoMessage} role="status">
              We couldn&apos;t find your location. Try again in a moment.
            </p>
          )}
        </>
      )}
    </fieldset>
  );
}

function ExploreContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => parseExploreParams(new URLSearchParams(searchParams.toString())), [searchParams]);
  const { q, trip, terrain, sort } = filters;
  const activeFilters = activeFilterCount(filters);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersId = useId();

  const [input, setInput] = useState(q);
  // Set while the box holds typing that hasn't reached the URL yet.
  const [typing, setTyping] = useState(false);
  const [seenQ, setSeenQ] = useState(q);
  if (q !== seenQ) {
    // The URL's search changed (a park link, Clear all, back button): show it.
    setSeenQ(q);
    if (!typing) setInput(q);
  }
  const savedTrails = useSavedTrails();
  const [units] = useUnits();
  const { status: authStatus } = useAuth();
  const resumedSave = useRef(false);
  const saveParam = searchParams.get("save");
  const returnTo = `/trail-list${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const [result, setResult] = useState<{
    key: string;
    trails: TrailSearchItem[] | null;
    total: number;
    facets: TrailFacets | null;
  } | null>(null);
  // Bumped by "Try again" so the same search is fetched afresh.
  const [attempt, setAttempt] = useState(0);

  // The searcher's position lives only here, in memory: never in the URL or
  // storage. Rounded to ~1 km before it's sent.
  const [geo, setGeo] = useState<{ status: GeoStatus; position?: { lat: number; lng: number } }>({ status: "idle" });

  // Every URL change here goes through history.replaceState, which Next keeps
  // useSearchParams in step with. Mixing it with router.replace doesn't work:
  // after the map writes its position, the router's next replace is undone
  // by its own stale copy of the URL.
  const updateUrl = useCallback((next: ExploreFilters) => {
    const search = keepViewParams(exploreSearch(next), new URLSearchParams(window.location.search));
    window.history.replaceState(null, "", search ? `/trail-list?${search}` : "/trail-list");
  }, []);

  const split = useSyncExternalStore(subscribeSplit, isSplit, () => false);
  const view: ExploreView = parseExploreView(searchParams);
  const mapVisible = split || view === "map";
  // Read once: afterwards the map owns its position and writes it back.
  const [initialMapView] = useState(() => parseMapView(new URLSearchParams(searchParams.toString())));
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const cardRefs = useRef(new Map<string, HTMLLIElement>());

  // View state goes straight into history: no navigation, no refetch.
  const setViewParam = useCallback((key: "map" | "view", value: string | null) => {
    const search = withViewParam(new URLSearchParams(window.location.search), key, value);
    window.history.replaceState(null, "", search ? `/trail-list?${search}` : "/trail-list");
  }, []);
  const onMapView = useCallback(
    (next: MapView) => setViewParam("map", formatMapView(next)),
    [setViewParam],
  );
  const showView = (next: ExploreView) => setViewParam("view", next === "map" ? "map" : null);

  // Picked on the map: bring its card into view, once the list is showing.
  useEffect(() => {
    if (!selectedId || !(split || view === "list")) return;
    cardRefs.current.get(selectedId)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedId, split, view]);

  // Geolocation answers arrive later; they apply to the filters as they are then.
  const latest = useRef(filters);
  useEffect(() => {
    latest.current = filters;
  }, [filters]);

  // Asks the browser; state changes only in its callbacks.
  const requestPosition = useCallback(() => {
    if (!("geolocation" in navigator)) {
      queueMicrotask(() => setGeo({ status: "unavailable" }));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const round = (n: number) => Math.round(n * 100) / 100;
        setGeo({
          status: "on",
          position: { lat: round(position.coords.latitude), lng: round(position.coords.longitude) },
        });
        const current = latest.current;
        if (!current.near) updateUrl({ ...current, near: true, sort: "nearest" });
      },
      (error) => {
        setGeo({ status: error.code === error.PERMISSION_DENIED ? "denied" : "unavailable" });
        if (latest.current.near) updateUrl(withoutNear(latest.current));
      },
      { enableHighAccuracy: false, maximumAge: 10 * 60 * 1000, timeout: 15000 },
    );
  }, [updateUrl]);

  if (!filters.near && geo.status === "stopped") setGeo({ status: "idle" });

  const locate = () => {
    setGeo({ status: "locating" });
    requestPosition();
  };

  // A shared or reloaded link with near=1: ask again (no prompt if allowed).
  // "idle" counts as waiting, so there's no "locating" step to set here.
  useEffect(() => {
    if (filters.near && geo.status === "idle") requestPosition();
  }, [filters.near, geo.status, requestPosition]);

  const stopNear = () => {
    setGeo({ status: "stopped" });
    updateUrl(withoutNear(filters));
  };

  // Typing updates the URL (debounced); the URL is what drives the fetch, so
  // links from the landing page and shared URLs behave the same as typing.
  useEffect(() => {
    if (!typing) return;
    const trimmed = input.trim();
    const timer = window.setTimeout(() => {
      setTyping(false);
      if (trimmed !== latest.current.q) updateUrl({ ...latest.current, q: trimmed });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [input, typing, updateUrl]);

  // Waiting on the browser for a position: hold the search rather than
  // flash results that aren't near anything.
  const waitingForPosition = filters.near && (geo.status === "idle" || geo.status === "locating");
  const request: TrailSearchRequest = {
    q,
    terrain,
    trip,
    provinces: filters.provinces,
    park_types: filters.parkTypes,
    parks: filters.parks,
    near:
      filters.near && geo.position
        ? { ...geo.position, ...(filters.within ? { radius_km: withinKm(filters.within) } : {}) }
        : undefined,
    bounds: filters.area,
    limit: RESULT_LIMIT,
  };
  const requestJson = JSON.stringify(request);
  // The map refits to each new search, but not to "Search this area".
  const searchKey = JSON.stringify({ ...request, bounds: undefined });
  const requestKey = `${requestJson}|${attempt}`;

  useEffect(() => {
    if (waitingForPosition) return;
    const controller = new AbortController();
    searchExplore(JSON.parse(requestJson) as TrailSearchRequest, controller.signal)
      .then((found) => setResult({ key: requestKey, trails: found.trails, total: found.total, facets: found.facets }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setResult((previous) => ({ key: requestKey, trails: null, total: 0, facets: previous?.facets ?? null }));
        }
      });
    return () => controller.abort();
  }, [requestJson, requestKey, waitingForPosition]);

  // Back from sign-in after a guest clicked Save on a card: finish that save.
  useEffect(() => {
    if (!saveParam || authStatus !== "signedIn" || savedTrails.loading || resumedSave.current) return;
    resumedSave.current = true;
    const done = () => updateUrl(latest.current);
    if (savedTrails.savedIds.has(saveParam)) done();
    else savedTrails.toggle(saveParam, true).catch(() => undefined).finally(done);
  }, [saveParam, authStatus, savedTrails, updateUrl]);

  // On phones the panel is a bottom sheet: keep the page behind it still.
  useEffect(() => {
    if (!filtersOpen || !window.matchMedia(MOBILE_QUERY).matches) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [filtersOpen]);

  const isLoading = result?.key !== requestKey;
  const fitKey = isLoading ? null : `${searchKey}|${attempt}`;
  const trails = result?.trails;
  const facets = result?.facets ?? null;
  const failed = !isLoading && trails === null;
  const sorted = trails ? sortTrails(trails, sort) : null;
  const titles = trailTitles(trails ?? []);
  const total = result?.total ?? 0;

  const parkProvinces = useMemo(
    () => new Map((facets?.parks ?? []).map((park) => [park.name, park.province_codes])),
    [facets],
  );
  const provinceOptions = (facets?.provinces ?? [])
    .map((p) => p.code)
    .concat(filters.provinces)
    .filter((code, index, all) => all.indexOf(code) === index)
    .sort(provinceOrder)
    .map((code) => ({
      value: code,
      label: provinceName(code),
      count: facets?.provinces.find((p) => p.code === code)?.count ?? 0,
    }));
  const parkTypeOptions = PARK_TYPES.map((type) => ({
    value: type,
    label: PARK_TYPE_LABELS[type],
    count: facets ? (facets.park_types.find((t) => t.type === type)?.count ?? 0) : null,
  }));
  const sorts = (Object.keys(TRAIL_SORT_LABELS) as TrailSort[]).filter(
    (option) => option !== "nearest" || (filters.near && geo.status === "on"),
  );

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTyping(false);
    updateUrl({ ...filters, q: input.trim() });
  };

  const setFilter = (next: ExploreFilters) => {
    // A new search can drop the picked trail, so its popup goes too.
    setSelectedId(null);
    updateUrl({ ...next, q: input.trim() });
  };
  const clearAll = () => {
    setGeo((current) => (filters.near ? { status: "stopped" } : current));
    setFilter(clearFilters(filters));
  };

  const removable: { key: string; label: string; next: ExploreFilters; onRemove?: () => void }[] = [
    ...(trip ? [{ key: "trip", label: TRIP_LABELS[trip], next: { ...filters, trip: undefined } }] : []),
    ...(terrain ? [{ key: "terrain", label: TERRAIN_LABELS[terrain], next: { ...filters, terrain: undefined } }] : []),
    ...filters.provinces.map((code) => ({
      key: `province:${code}`,
      label: provinceName(code),
      next: withProvinces(filters, filters.provinces.filter((p) => p !== code), parkProvinces),
    })),
    ...filters.parkTypes.map((type) => ({
      key: `type:${type}`,
      label: type === "other" ? "Other (not a national or provincial park)" : PARK_TYPE_LABELS[type],
      next: { ...filters, parkTypes: filters.parkTypes.filter((t) => t !== type) },
    })),
    ...filters.parks.map((park) => ({
      key: `park:${park}`,
      label: park,
      next: { ...filters, parks: filters.parks.filter((p) => p !== park) },
    })),
    ...(filters.near
      ? [{
          key: "near",
          label: filters.within ? `${withinLabel(filters.within)} of you` : "Near you",
          next: withoutNear(filters),
          onRemove: () => setGeo({ status: "stopped" }),
        }]
      : []),
    ...(filters.area ? [{ key: "area", label: "In the map area", next: { ...filters, area: undefined } }] : []),
  ];

  const searchArea = (bounds: Bounds) => setFilter({ ...filters, area: bounds });
  const toggleNear = () => (filters.near ? stopNear() : locate());
  const showMapLabel = view === "map" ? "Show list" : "Show map";

  return (
    <main className={styles.page} data-view={view}>
      <h1 className={ui.srOnly}>Explore trails</h1>

      <div className={styles.layout}>
        <div className={styles.listPane}>
          <div className={styles.controls}>
            <form className={styles.searchBar} onSubmit={handleSubmit} role="search">
              <input
                className={styles.searchInput}
                type="search"
                placeholder="Search trails, parks or regions…"
                aria-label="Search trails, parks or regions"
                autoComplete="off"
                value={input}
                onChange={(event) => {
                  setInput(event.target.value);
                  setTyping(true);
                }}
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

            {/* Shortcuts into the same filters as the panel. */}
            <div className={styles.quickChips} role="group" aria-label="Quick filters">
              {(["day", "overnight"] as TripType[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  className={styles.chip}
                  aria-pressed={trip === value}
                  onClick={() => setFilter(toggleTrip(filters, value))}
                >
                  {TRIP_LABELS[value]}
                </button>
              ))}
              {QUICK_PARKS.map(({ park, label }) => (
                <button
                  key={park}
                  type="button"
                  className={styles.chip}
                  aria-pressed={filters.parks.includes(park)}
                  onClick={() => setFilter({ ...filters, parks: toggle(filters.parks, park) })}
                >
                  {label}
                </button>
              ))}
              <button
                type="button"
                className={styles.chip}
                aria-pressed={filters.near}
                onClick={toggleNear}
                disabled={geo.status === "locating"}
              >
                <svg viewBox="0 0 20 20" aria-hidden="true" className={styles.chipIcon}>
                  <circle cx="10" cy="10" r="2.6" fill="currentColor" />
                  <circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" strokeWidth="1.7" />
                </svg>
                {geo.status === "locating" ? "Finding you…" : "Near me"}
              </button>
            </div>
            {(geo.status === "denied" || geo.status === "unavailable") && !filtersOpen && (
              <p className={styles.geoMessage} role="status">
                {geo.status === "denied"
                  ? "Location access is blocked. Allow it for Trekly in your browser to search near you."
                  : "We couldn't find your location. Try again in a moment."}
              </p>
            )}

            {filtersOpen && (
              <>
                <div className={styles.sheetBackdrop} aria-hidden="true" onClick={() => setFiltersOpen(false)} />
                <div
                  id={filtersId}
                  className={styles.filterPanel}
                  role="region"
                  aria-label="Filters"
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setFiltersOpen(false);
                  }}
                >
                  <div className={styles.sheetHandle} aria-hidden="true" />
                  <div className={styles.filterBody}>
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
                    <CountChipGroup
                      label="Province"
                      options={provinceOptions}
                      selected={filters.provinces}
                      onToggle={(code) =>
                        setFilter(withProvinces(filters, toggle(filters.provinces, code), parkProvinces))
                      }
                    />
                    <CountChipGroup
                      label="Park type"
                      options={parkTypeOptions}
                      selected={filters.parkTypes}
                      onToggle={(type) =>
                        setFilter({ ...filters, parkTypes: toggle(filters.parkTypes, type as ParkTypeFilter) })
                      }
                    />
                    <ParkPicker
                      parks={facets?.parks ?? []}
                      selected={filters.parks}
                      provinces={filters.provinces}
                      onToggle={(park) => setFilter({ ...filters, parks: toggle(filters.parks, park) })}
                    />
                    <NearMe
                      filters={filters}
                      status={geo.status}
                      units={units}
                      onLocate={locate}
                      onStop={stopNear}
                      onWithin={(value) =>
                        setFilter({
                          ...filters,
                          within: value ? { value, unit: units === "imperial" ? "mi" : "km" } : undefined,
                        })
                      }
                    />
                  </div>
                  <div className={styles.filterFooter}>
                    {activeFilters > 0 && (
                      <button type="button" className={ui.ghost} onClick={clearAll}>
                        Clear all
                      </button>
                    )}
                    <button
                      type="button"
                      className={`${ui.secondary} ${styles.doneButton}`}
                      onClick={() => setFiltersOpen(false)}
                    >
                      Done
                    </button>
                    <button type="button" className={`${ui.primary} ${styles.showButton}`} onClick={() => setFiltersOpen(false)}>
                      {isLoading && !result ? "Show trails" : `Show ${total} ${total === 1 ? "trail" : "trails"}`}
                    </button>
                  </div>
                </div>
              </>
            )}

            {removable.length > 0 && (
              <div className={styles.activeRow}>
                <ul className={styles.activeFilters} aria-label="Active filters">
                  {removable.map((chip) => (
                    <li key={chip.key}>
                      <button
                        type="button"
                        className={styles.activeChip}
                        onClick={() => {
                          chip.onRemove?.();
                          setFilter(chip.next);
                        }}
                        aria-label={`Remove filter: ${chip.label}`}
                      >
                        {chip.label} <span aria-hidden="true">×</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <button type="button" className={styles.clearAll} onClick={clearAll}>
                  Clear all
                </button>
              </div>
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
              <>
                <p className={styles.count}>
                  {waitingForPosition ? "Finding trails near you…" : "Loading trails…"}
                </p>
                <ul className={styles.list}>
                  {Array.from({ length: SKELETON_CARDS }, (_, index) => (
                    <TrailCardSkeleton key={index} />
                  ))}
                </ul>
              </>
            ) : sorted.length === 0 ? (
              <p className={styles.status}>
                No trails match
                {q ? <> &ldquo;{q}&rdquo;</> : null}
                {activeFilters > 0 ? <> with these filters</> : null}
                {filters.area ? <> in this map area</> : null}. Try a broader search or remove a filter.
              </p>
            ) : (
              <>
                <div className={styles.resultsHead}>
                  {/* The API caps the catalogue at RESULT_LIMIT, so this count is exact. */}
                  <p className={styles.count}>
                    {total}{" "}
                    {trip === "overnight" ? "backpacking " : trip === "day" ? "day-hike " : ""}
                    {total === 1 ? "trail" : "trails"}
                    {q ? <> matching &ldquo;{q}&rdquo;</> : null}
                  </p>
                  <label className={styles.sort}>
                    <span className={styles.sortLabel}>Sort</span>
                    <select
                      className={ui.input}
                      value={sort}
                      onChange={(event) => setFilter({ ...filters, sort: event.target.value as TrailSort })}
                    >
                      {sorts.map((option) => (
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
                      ref={(node) => {
                        if (node) cardRefs.current.set(trail.id, node);
                        else cardRefs.current.delete(trail.id);
                      }}
                      trail={trail}
                      title={titles.get(trail.id) ?? trail.name}
                      saved={savedTrails.savedIds.has(trail.id)}
                      pending={savedTrails.pending.has(trail.id)}
                      onToggleSave={savedTrails.toggle}
                      returnTo={returnTo}
                      units={units}
                      selected={selectedId === trail.id}
                      onHover={setHoveredId}
                    />
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>

        {mapVisible && (
          <div className={styles.mapPane}>
            <ExploreMap
              trails={sorted ?? []}
              titles={titles}
              hoveredId={hoveredId}
              selectedId={selectedId}
              initialView={initialMapView}
              fitKey={fitKey}
              areaActive={Boolean(filters.area)}
              onSelect={setSelectedId}
              onOpen={(id) => router.push(`/trails?id=${encodeURIComponent(id)}`)}
              onViewChange={onMapView}
              onSearchArea={searchArea}
            />
          </div>
        )}
      </div>

      {/* Below the split layout: one at a time. */}
      <button
        type="button"
        className={styles.viewToggle}
        onClick={() => showView(view === "map" ? "list" : "map")}
      >
        {view === "map" ? (
          <svg viewBox="0 0 20 20" aria-hidden="true" className={styles.filterIcon}>
            <path d="M4 5h12M4 10h12M4 15h12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 20 20" aria-hidden="true" className={styles.filterIcon}>
            <path
              d="M2.5 5l5-2 5 2 5-2v12l-5 2-5-2-5 2zM7.5 3v12M12.5 5v12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
        )}
        {showMapLabel}
      </button>
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
