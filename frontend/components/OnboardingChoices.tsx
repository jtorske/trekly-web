"use client";

import { useCallback, useEffect, useId, useState, type ReactNode } from "react";
import { Check, LocateFixed, Search } from "lucide-react";
import { EXPERIENCE_LEVELS, HIKING_STYLES, REGIONS, type Choice } from "@/lib/onboarding";
import { PROVINCE_NAMES } from "@/lib/exploreFilters";
import { regionChips, sortOrigin, type Point, type RegionChip } from "@/lib/regionOrder";
import { formatWholeDistance, type UnitSystem } from "@/lib/units";
import styles from "./OnboardingChoices.module.css";

/**
 * Big tappable choices for the /welcome flow and Settings → Trail
 * preferences. They're real radio buttons and checkboxes under the cards, so
 * arrow keys, Space and screen readers work as they do for any form.
 */

export interface CardOption<T extends string> extends Choice<T> {
  icon?: ReactNode;
  /** Extra content under the hint, e.g. a sample distance. */
  extra?: ReactNode;
}

export function ChoiceCards<T extends string>({
  legend,
  options,
  value,
  onChange,
  columns = 3,
  hideLegend = true,
}: {
  legend: string;
  options: CardOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  columns?: 1 | 2 | 3;
  hideLegend?: boolean;
}) {
  const name = useId();
  return (
    <fieldset className={styles.fieldset}>
      <legend className={hideLegend ? styles.srOnly : styles.legend}>{legend}</legend>
      <div className={styles.cards} data-columns={columns}>
        {options.map((option) => {
          const checked = value === option.value;
          return (
            <label key={option.value} className={styles.card} data-checked={checked || undefined}>
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={checked}
                onChange={() => onChange(option.value)}
                className={styles.input}
              />
              {option.icon && (
                <span className={styles.cardIcon} aria-hidden="true">
                  {option.icon}
                </span>
              )}
              <span className={styles.cardText}>
                <span className={styles.cardLabel}>{option.label}</span>
                <span className={styles.cardHint}>{option.hint}</span>
                {option.extra}
              </span>
              <span className={styles.tick} aria-hidden="true">
                <Check size={14} strokeWidth={3} />
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function ChipChecks({
  legend,
  options,
  values,
  onToggle,
  hideLegend = true,
  empty,
}: {
  legend: string;
  options: { value: string; label: string; sub?: string }[];
  values: string[];
  onToggle: (value: string) => void;
  hideLegend?: boolean;
  empty?: ReactNode;
}) {
  return (
    <fieldset className={styles.fieldset}>
      <legend className={hideLegend ? styles.srOnly : styles.legend}>{legend}</legend>
      {options.length === 0 && empty}
      <div className={styles.chips}>
        {options.map((option) => {
          const checked = values.includes(option.value);
          return (
            <label key={option.value} className={styles.chip} data-checked={checked || undefined}>
              <input type="checkbox" checked={checked} onChange={() => onToggle(option.value)} className={styles.input} />
              <span className={styles.chipTick} aria-hidden="true">
                <Check size={14} strokeWidth={3} />
              </span>
              <span>{option.label}</span>
              {option.sub && <span className={styles.chipSub}>{option.sub}</span>}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function toggleValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}

export function HikingStyleCards({
  value,
  onChange,
  icons,
}: {
  value: string | null;
  onChange: (value: (typeof HIKING_STYLES)[number]["value"]) => void;
  icons?: Record<string, ReactNode>;
}) {
  return (
    <ChoiceCards
      legend="How do you like to hike?"
      options={HIKING_STYLES.map((option) => ({ ...option, icon: icons?.[option.value] }))}
      value={value as (typeof HIKING_STYLES)[number]["value"] | null}
      onChange={onChange}
    />
  );
}

export function ExperienceCards({
  value,
  onChange,
  icons,
}: {
  value: string | null;
  onChange: (value: (typeof EXPERIENCE_LEVELS)[number]["value"]) => void;
  icons?: Record<string, ReactNode>;
}) {
  return (
    <ChoiceCards
      legend="How much trail time do you have?"
      options={EXPERIENCE_LEVELS.map((option) => ({ ...option, icon: icons?.[option.value] }))}
      value={value as (typeof EXPERIENCE_LEVELS)[number]["value"] | null}
      onChange={onChange}
    />
  );
}

type Located = { state: "idle" | "locating" | "denied" | "failed" } | { state: "found"; point: Point };

/**
 * The browser's location for sorting parks, kept in this component only:
 * never sent to the server or saved. If the site already has permission it's
 * read straight away; otherwise nothing is asked until `locate` is called
 * (the "Use my exact location" button), so no prompt pops up on page load.
 */
function useSortLocation(enabled: boolean): { located: Located; locate: () => void } {
  const [located, setLocated] = useState<Located>({ state: "idle" });

  const locate = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setLocated({ state: "failed" });
      return;
    }
    setLocated({ state: "locating" });
    navigator.geolocation.getCurrentPosition(
      (position) => setLocated({ state: "found", point: { lat: position.coords.latitude, lon: position.coords.longitude } }),
      (error) => setLocated({ state: error.code === error.PERMISSION_DENIED ? "denied" : "failed" }),
      { maximumAge: 10 * 60 * 1000, timeout: 10_000 },
    );
  }, []);

  useEffect(() => {
    if (!enabled || !navigator.permissions?.query || !("geolocation" in navigator)) return;
    let live = true;
    navigator.permissions
      .query({ name: "geolocation" })
      .then((status) => {
        if (!live) return;
        if (status.state === "granted") locate();
        else if (status.state === "denied") setLocated({ state: "denied" });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [enabled, locate]);

  return { located, locate };
}

/**
 * Parks and regions, with a search box. Picks stay picked while searching,
 * and show at the top once a search starts.
 *
 * With `sortFrom` (the /welcome flow), parks come nearest first: from the
 * browser's location when allowed, else the centre of their home province,
 * each chip showing how far away it is.
 */
export function RegionPicker({
  values,
  onChange,
  sortFrom,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  sortFrom?: { home: string | null; units: UnitSystem };
}) {
  const [query, setQuery] = useState("");
  // Picks as of the last search: they sit at the top. A chip tapped now stays
  // where it is (no jumping under the finger) until the search changes.
  const [pinned, setPinned] = useState<string[]>(values);
  const searchId = useId();
  const { located, locate } = useSortLocation(Boolean(sortFrom));
  const origin = sortFrom ? sortOrigin(located.state === "found" ? located.point : null, sortFrom.home) : null;
  const chips = regionChips({ query, pinned, origin, provinceNames: PROVINCE_NAMES });
  const picked = REGIONS.filter((region) => values.includes(region.slug));

  const option = ({ region, km }: RegionChip) => ({
    value: region.slug,
    label: region.label,
    sub: km === null || !sortFrom ? region.province : `${region.province} · ${formatWholeDistance(km, sortFrom.units)}`,
  });

  const canAsk = Boolean(sortFrom) && origin?.kind !== "here" && located.state !== "denied";
  const sortNote =
    origin?.kind === "here"
      ? "Nearest to you first."
      : origin?.kind === "home"
        ? `Nearest to the middle of ${PROVINCE_NAMES[origin.province] ?? origin.province} first.`
        : null;

  return (
    <div className={styles.regions}>
      <label className={styles.search} htmlFor={searchId}>
        <Search size={18} aria-hidden="true" className={styles.searchIcon} />
        <span className={styles.srOnly}>Search parks and regions</span>
        <input
          id={searchId}
          type="search"
          value={query}
          placeholder="Search parks, regions or provinces"
          onChange={(event) => {
            setQuery(event.target.value);
            setPinned(values);
          }}
          // A search box filters; Enter here shouldn't move on to the next screen.
          onKeyDown={(event) => {
            if (event.key === "Enter") event.preventDefault();
          }}
          autoComplete="off"
          aria-describedby={`${searchId}-count`}
        />
      </label>
      {(sortNote || canAsk) && (
        <div className={styles.sortRow}>
          {sortNote && <p className={styles.sortNote}>{sortNote}</p>}
          {canAsk && (
            <button type="button" className={styles.locate} onClick={locate} disabled={located.state === "locating"}>
              <LocateFixed size={16} aria-hidden="true" />
              {located.state === "locating" ? "Finding you…" : "Use my exact location"}
            </button>
          )}
          {located.state === "failed" && (
            <p className={styles.sortNote} role="status">
              We couldn&apos;t get your location just now.
            </p>
          )}
        </div>
      )}
      <p id={`${searchId}-count`} className={styles.count} aria-live="polite">
        {picked.length === 0
          ? "Nothing picked yet."
          : `${picked.length} picked: ${picked.map((region) => region.label).join(", ")}.`}
      </p>
      <ChipChecks
        legend="Parks and regions"
        options={[...chips.pinned, ...chips.others].map(option)}
        values={values}
        onToggle={(value) => onChange(toggleValue(values, value))}
      />
      {chips.others.length === 0 && query.trim() && (
        <p className={styles.empty}>
          No {chips.pinned.length ? "other " : ""}parks match &ldquo;{query.trim()}&rdquo;. Try a province, like Alberta.
        </p>
      )}
    </div>
  );
}
