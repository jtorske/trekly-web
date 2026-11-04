"use client";

import { useId, useState, type ReactNode } from "react";
import { Check, Search } from "lucide-react";
import { EXPERIENCE_LEVELS, HIKING_STYLES, INTERESTS, REGIONS, searchRegions, type Choice } from "@/lib/onboarding";
import { PROVINCE_NAMES } from "@/lib/exploreFilters";
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

export function InterestChips({ values, onChange }: { values: string[]; onChange: (values: string[]) => void }) {
  return (
    <ChipChecks
      legend="What gets you out there? Pick any."
      options={INTERESTS}
      values={values}
      onToggle={(value) => onChange(toggleValue(values, value))}
    />
  );
}

/** Parks and regions, with a search box; picks stay picked while searching. */
export function RegionPicker({ values, onChange }: { values: string[]; onChange: (values: string[]) => void }) {
  const [query, setQuery] = useState("");
  const searchId = useId();
  const shown = searchRegions(query, PROVINCE_NAMES);
  const picked = REGIONS.filter((region) => values.includes(region.slug));
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
          onChange={(event) => setQuery(event.target.value)}
          // A search box filters; Enter here shouldn't move on to the next screen.
          onKeyDown={(event) => {
            if (event.key === "Enter") event.preventDefault();
          }}
          autoComplete="off"
          aria-describedby={`${searchId}-count`}
        />
      </label>
      <p id={`${searchId}-count`} className={styles.count} aria-live="polite">
        {picked.length === 0
          ? "Nothing picked yet."
          : `${picked.length} picked: ${picked.map((region) => region.label).join(", ")}.`}
      </p>
      <ChipChecks
        legend="Parks and regions"
        options={shown.map((region) => ({ value: region.slug, label: region.label, sub: region.province }))}
        values={values}
        onToggle={(value) => onChange(toggleValue(values, value))}
        empty={<p className={styles.empty}>No parks match &ldquo;{query.trim()}&rdquo;. Try a province, like Alberta.</p>}
      />
    </div>
  );
}
