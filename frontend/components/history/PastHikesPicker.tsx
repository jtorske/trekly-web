"use client";

import { useEffect, useId, useMemo, useState } from "react";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import {
  PICKER_SORTS,
  filterProvinces,
  groupForPicker,
  groupHeading,
  hasSharedName,
  mergeTrails,
  orderForPicker,
  pickerProvinces,
  placeLine,
  searchPicker,
  sharedNames,
  sortForPicker,
  type PickerPreferences,
  type PickerSort,
} from "@/lib/pastHikes";
import { province as findProvince } from "@/lib/provinces";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import styles from "./PastHikesPicker.module.css";

/** Park groups open to begin with; the rest start folded. */
const OPEN_AT_START = 2;

type Location =
  | { state: "idle" }
  | { state: "locating" }
  | { state: "found"; lat: number; lon: number }
  | { state: "unavailable" };

const provinceName = (code: string) => findProvince(code)?.name ?? code;

/**
 * "Which of these have you hiked?": trail cards to tap, grouped by park (or
 * in a flat order), with province chips and search. The parent owns the
 * selection and saves it (onboarding's /welcome step and the journal's "Add
 * past hikes" dialog both use this). Trails already in the journal show as
 * such and can't be picked again.
 *
 * "Nearest to me" asks the browser for its location once, when chosen, and
 * uses it only to order the list; it's never sent anywhere or kept.
 */
export default function PastHikesPicker({
  catalogue,
  logged,
  selected,
  onToggle,
  preferences,
}: {
  catalogue: TrailListItem[];
  /** Trail ids already in the journal. */
  logged: ReadonlySet<string>;
  selected: ReadonlySet<string>;
  onToggle: (trailId: string) => void;
  preferences?: PickerPreferences;
}) {
  const searchId = useId();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<PickerSort>("park");
  const [provinces, setProvinces] = useState<ReadonlySet<string>>(() => new Set());
  const [location, setLocation] = useState<Location>({ state: "idle" });
  const [remote, setRemote] = useState<{ query: string; trails: TrailListItem[] } | null>(null);

  const shared = useMemo(() => sharedNames(catalogue), [catalogue]);
  const chips = useMemo(() => pickerProvinces(catalogue), [catalogue]);
  const inProvinces = useMemo(() => filterProvinces(catalogue, provinces), [catalogue, provinces]);
  const groups = useMemo(() => groupForPicker(inProvinces, preferences, provinceName), [inProvinces, preferences]);
  // Groups the hiker opened or closed; the rest follow OPEN_AT_START, so the
  // first groups of any filter start open.
  const [toggled, setToggled] = useState<ReadonlyMap<string, boolean>>(() => new Map());

  // Searching shows a flat list; the catalogue holds the most popular trails,
  // so a search also asks the server for less popular ones.
  const trimmed = query.trim();
  useEffect(() => {
    if (trimmed.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchTrails(trimmed, controller.signal, { limit: 20 })
        .then((trails) => setRemote({ query: trimmed, trails }))
        .catch(() => undefined);
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  const searching = trimmed.length > 0;
  const found = useMemo(() => {
    if (!searching) return [];
    const local = searchPicker(orderForPicker(inProvinces, preferences), query);
    const extra = remote && remote.query === trimmed && trimmed.length >= 2 ? filterProvinces(remote.trails, provinces) : [];
    return mergeTrails(local, extra);
  }, [searching, inProvinces, preferences, query, remote, trimmed, provinces]);

  const here = location.state === "found" ? { lat: location.lat, lon: location.lon } : null;
  const flat = useMemo(
    () => (sort === "park" ? [] : sortForPicker(inProvinces, sort, here)),
    // `here` is rebuilt each render; its coordinates are what matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [inProvinces, sort, here?.lat, here?.lon],
  );

  const chooseSort = (next: PickerSort) => {
    setSort(next);
    if (next !== "nearest" || location.state === "found" || location.state === "locating") return;
    if (!("geolocation" in navigator)) {
      setLocation({ state: "unavailable" });
      return;
    }
    setLocation({ state: "locating" });
    navigator.geolocation.getCurrentPosition(
      (position) => setLocation({ state: "found", lat: position.coords.latitude, lon: position.coords.longitude }),
      () => setLocation({ state: "unavailable" }),
      { maximumAge: 10 * 60 * 1000, timeout: 10_000 },
    );
  };

  const toggleProvince = (code: string) =>
    setProvinces((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });

  const toggleGroup = (key: string, isOpen: boolean) =>
    setToggled((current) => (current.get(key) === isOpen ? current : new Map(current).set(key, isOpen)));

  const card = (trail: TrailListItem, showPlace: boolean) => {
    const inJournal = logged.has(trail.id);
    const on = inJournal || selected.has(trail.id);
    // Same-named trails always say where they are, even inside a park's group.
    const line = inJournal
      ? "In your journal"
      : showPlace || hasSharedName(trail, shared)
        ? placeLine(trail, shared, catalogue)
        : null;
    return (
      <li key={trail.id}>
        <button
          type="button"
          className={`${styles.card} ${on ? styles.on : ""}`}
          aria-pressed={on}
          disabled={inJournal}
          onClick={() => onToggle(trail.id)}
        >
          <span className={styles.photo}>
            <TrailPhoto photo={trail.photo} name={trail.name} variant="thumb" />
            <span className={styles.tick} aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="m5 12.5 4.2 4.2L19 7" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          </span>
          <span className={styles.name}>{trail.name}</span>
          {line && <span className={styles.park}>{line}</span>}
        </button>
      </li>
    );
  };

  return (
    <div className={styles.picker}>
      <label className={styles.search} htmlFor={searchId}>
        <span className={ui.srOnly}>Search trails</span>
        <input
          id={searchId}
          type="search"
          className={ui.input}
          placeholder="Search trails, parks or regions"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
      </label>

      <div className={styles.controls}>
        <div className={styles.sorts} role="radiogroup" aria-label="Order trails">
          {PICKER_SORTS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={sort === option.value}
              className={`${styles.sort} ${sort === option.value ? styles.sortOn : ""}`}
              onClick={() => chooseSort(option.value)}
              disabled={searching}
            >
              {option.label}
            </button>
          ))}
        </div>
        {chips.length > 1 && (
          <div className={styles.chips} role="group" aria-label="Provinces">
            {chips.map((code) => (
              <button
                key={code}
                type="button"
                aria-pressed={provinces.has(code)}
                className={`${styles.chip} ${provinces.has(code) ? styles.chipOn : ""}`}
                onClick={() => toggleProvince(code)}
                title={provinceName(code)}
              >
                {provinceName(code)}
              </button>
            ))}
          </div>
        )}
      </div>

      {!searching && sort === "nearest" && location.state !== "found" && (
        <p className={styles.notice} role="status">
          {location.state === "locating"
            ? "Finding trails near you…"
            : "Your location isn't available, so these are by popularity instead."}
        </p>
      )}

      {searching ? (
        found.length === 0 ? (
          <p className={styles.empty}>No trails match &ldquo;{query}&rdquo;.</p>
        ) : (
          <ul className={styles.grid} aria-label="Matching trails">
            {found.map((trail) => card(trail, true))}
          </ul>
        )
      ) : sort === "park" ? (
        groups.length === 0 ? (
          <p className={styles.empty}>No trails in those provinces.</p>
        ) : (
          <div className={styles.groups}>
            {groups.map((group, index) => {
              const picked = group.trails.filter((trail) => selected.has(trail.id)).length;
              const isOpen = toggled.get(group.key) ?? index < OPEN_AT_START;
              return (
                <details
                  key={group.key}
                  className={styles.group}
                  open={isOpen}
                  onToggle={(event) => toggleGroup(group.key, event.currentTarget.open)}
                >
                  <summary className={styles.groupSummary}>
                    <span className={styles.groupTitle}>{groupHeading(group)}</span>
                    {group.province && <span className={styles.groupProvince}>{provinceName(group.province)}</span>}
                    {picked > 0 && <span className={styles.groupPicked}>{picked} picked</span>}
                  </summary>
                  {/* Cards render only while open, so 100+ thumbnails don't load at once. */}
                  {isOpen && <ul className={styles.grid}>{group.trails.map((trail) => card(trail, false))}</ul>}
                </details>
              );
            })}
          </div>
        )
      ) : flat.length === 0 ? (
        <p className={styles.empty}>No trails in those provinces.</p>
      ) : (
        <ul className={styles.grid} aria-label="Trails">
          {flat.map((trail) => card(trail, true))}
        </ul>
      )}
    </div>
  );
}
