"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import { searchTrails, type Trail } from "./campsites";
import {
  CampsiteIcon,
  CheckBadgeIcon,
  SearchIcon,
  TrailPinIcon,
} from "./icons";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const WEEKDAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

const MAX_ARRIVAL_DATES = 28;

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function isoDate(year: number, monthIndex: number, day: number) {
  return `${year}-${pad(monthIndex + 1)}-${pad(day)}`;
}

function daysInMonth(year: number, monthIndex: number) {
  return new Date(year, monthIndex + 1, 0).getDate();
}

function firstWeekday(year: number, monthIndex: number) {
  return new Date(year, monthIndex, 1).getDay();
}

function SuccessPanel({
  trail,
  onReset,
}: {
  trail: Trail;
  onReset: () => void;
}) {
  return (
    <div className={styles.success}>
      <CheckBadgeIcon className={styles.successIcon} />
      <h1 className={styles.successTitle}>Your alert is set</h1>
      <p className={styles.successBody}>
        We&apos;ll email you the moment a matching opening turns up at{" "}
        {trail.name}. You can manage or cancel this alert anytime from your
        account.
      </p>
      <button type="button" className={styles.successButton} onClick={onReset}>
        Create another alert
      </button>
    </div>
  );
}

export default function CampAlertPage() {
  const today = useMemo(() => new Date(), []);
  const todayISO = useMemo(
    () => isoDate(today.getFullYear(), today.getMonth(), today.getDate()),
    [today],
  );

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Trail[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedTrail, setSelectedTrail] = useState<Trail | null>(null);

  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());

  const [nights, setNights] = useState(1);

  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!query.trim() || selectedTrail) {
      return;
    }

    let ignore = false;

    async function run() {
      setIsSearching(true);
      const found = await searchTrails(query);
      if (!ignore) {
        setResults(found);
        setIsSearching(false);
      }
    }

    run();

    return () => {
      ignore = true;
    };
  }, [query, selectedTrail]);

  const canSubmit =
    !!selectedTrail &&
    selectedDates.size > 0 &&
    nights >= 1 &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  function handleSelectTrail(trail: Trail) {
    setSelectedTrail(trail);
    setQuery(trail.name);
    setResults([]);
    setSelectedDates(new Set());
    setNights(1);
  }

  function handleChangeTrail() {
    setSelectedTrail(null);
    setQuery("");
    setResults([]);
  }

  function toggleDate(iso: string) {
    setSelectedDates((current) => {
      const next = new Set(current);
      if (next.has(iso)) {
        next.delete(iso);
      } else {
        if (next.size >= MAX_ARRIVAL_DATES) return current;
        next.add(iso);
      }
      return next;
    });
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setIsSubmitting(true);
    window.setTimeout(() => {
      setIsSubmitting(false);
      setSubmitted(true);
    }, 700);
  }

  function handleReset() {
    setSubmitted(false);
    setSelectedTrail(null);
    setQuery("");
    setSelectedDates(new Set());
    setNights(1);
    setEmail("");
  }

  if (submitted && selectedTrail) {
    return (
      <main className={styles.page}>
        <SuccessPanel trail={selectedTrail} onReset={handleReset} />
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.intro}>
        <h1 className={styles.title}>CampAlert</h1>
        <p className={styles.subtitle}>
          Get notified the moment a spot opens up at the campground, hut, or
          backcountry site you want.
        </p>
      </div>

      <div className={styles.searchWrap}>
        <div className={styles.searchBar}>
          <SearchIcon className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search for a backcountry site"
            aria-label="Search for a campground, caravan park, hut, backcountry site, or shuttle"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setSelectedTrail(null);
            }}
          />
          {query && (
            <button
              type="button"
              className={styles.searchClear}
              onClick={handleChangeTrail}
            >
              Clear
            </button>
          )}
        </div>

        {!selectedTrail && query.trim() && (
          <div
            className={styles.results}
            role="listbox"
            aria-label="Matching campsites"
          >
            {isSearching ? (
              <p className={styles.resultEmpty}>Searching…</p>
            ) : results.length === 0 ? (
              <p className={styles.resultEmpty}>
                No matches yet — try a different name or region.
              </p>
            ) : (
              results.map((trail) => (
                <button
                  key={trail.id}
                  type="button"
                  role="option"
                  aria-selected="false"
                  className={styles.resultItem}
                  onClick={() => handleSelectTrail(trail)}
                >
                  <TrailPinIcon className={styles.resultIcon} />
                  <span>
                    <span className={styles.resultName}>{trail.name}</span>
                    <span className={styles.resultMeta}>{trail.region}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {selectedTrail && (
        <div className={styles.selectedBar}>
          <div className={styles.selectedInfo}>
            <TrailPinIcon className={styles.selectedIcon} />
            <span>
              <span className={styles.selectedName}>{selectedTrail.name}</span>
              <span className={styles.selectedMeta}>
                {selectedTrail.region}
              </span>
            </span>
          </div>
          <button
            type="button"
            className={styles.changeButton}
            onClick={handleChangeTrail}
          >
            Change
          </button>
        </div>
      )}

      {!selectedTrail ? (
        <div className={styles.emptyState}>
          <CampsiteIcon className={styles.emptyMark} />
          <p>
            Search above to set up an alert for a specific backcountry site.
          </p>
        </div>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          <section className={styles.section}>
            <span className={styles.stepBadge}>1</span>
            <div className={styles.sectionBody}>
              <h2 className={styles.sectionTitle}>Select your arrival dates</h2>
              <p className={styles.sectionDesc}>
                These are days you want to start your stay. If you want a
                weekend, pick only the Friday.
              </p>

              <div className={styles.fieldLabel}>
                <span>What days can you arrive?*</span>
                <span
                  className={`${styles.fieldCount} ${
                    selectedDates.size >= MAX_ARRIVAL_DATES
                      ? styles.fieldCountLimit
                      : ""
                  }`}
                >
                  {selectedDates.size} selected
                </span>
              </div>

              <div className={styles.calendarNav}>
                <select
                  className={styles.calendarSelect}
                  value={viewMonth}
                  aria-label="Month"
                  onChange={(event) => setViewMonth(Number(event.target.value))}
                >
                  {MONTH_NAMES.map((month, index) => (
                    <option
                      key={month}
                      value={index}
                      disabled={
                        viewYear === today.getFullYear() &&
                        index < today.getMonth()
                      }
                    >
                      {month}
                    </option>
                  ))}
                </select>
                <select
                  className={styles.calendarSelect}
                  value={viewYear}
                  aria-label="Year"
                  onChange={(event) => setViewYear(Number(event.target.value))}
                >
                  <option value={today.getFullYear()}>
                    {today.getFullYear()}
                  </option>
                  <option value={today.getFullYear() + 1}>
                    {today.getFullYear() + 1}
                  </option>
                </select>
              </div>

              <div className={styles.calendar}>
                <div className={styles.calendarWeekdays}>
                  {WEEKDAY_LABELS.map((day) => (
                    <span key={day} className={styles.calendarWeekday}>
                      {day}
                    </span>
                  ))}
                </div>
                <div className={styles.calendarGrid}>
                  {Array.from({
                    length: firstWeekday(viewYear, viewMonth),
                  }).map((_, index) => (
                    <span
                      key={`pad-${index}`}
                      className={styles.calendarCell}
                      aria-hidden="true"
                    />
                  ))}
                  {Array.from({ length: daysInMonth(viewYear, viewMonth) }).map(
                    (_, index) => {
                      const day = index + 1;
                      const iso = isoDate(viewYear, viewMonth, day);
                      const isPast = iso < todayISO;
                      const isSelected = selectedDates.has(iso);

                      return (
                        <span key={iso} className={styles.calendarCell}>
                          <button
                            type="button"
                            className={`${styles.calendarDay} ${
                              isSelected ? styles.calendarDaySelected : ""
                            }`}
                            disabled={isPast}
                            aria-pressed={isSelected}
                            aria-label={iso}
                            onClick={() => toggleDate(iso)}
                          >
                            {day}
                          </button>
                        </span>
                      );
                    },
                  )}
                </div>
              </div>
              <p className={styles.calendarHint}>
                Select up to {MAX_ARRIVAL_DATES} different days.
              </p>
            </div>
          </section>

          <section className={styles.section}>
            <span className={styles.stepBadge}>2</span>
            <div className={styles.sectionBody}>
              <h2 className={styles.sectionTitle}>Select your nights</h2>
              <p className={styles.sectionDesc}>
                Fewer nights means more notifications.
              </p>

              <div className={styles.fieldLabel}>
                <span>How many nights would you like to stay?*</span>
              </div>

              <div className={styles.stepper}>
                <button
                  type="button"
                  className={styles.stepperButton}
                  aria-label="Decrease nights"
                  disabled={nights <= 1}
                  onClick={() => setNights((n) => Math.max(1, n - 1))}
                >
                  −
                </button>
                <span className={styles.stepperValue}>
                  {nights} {nights === 1 ? "night" : "nights"}
                </span>
                <button
                  type="button"
                  className={styles.stepperButton}
                  aria-label="Increase nights"
                  disabled={nights >= 30}
                  onClick={() => setNights((n) => Math.min(30, n + 1))}
                >
                  +
                </button>
              </div>
            </div>
          </section>

          <section className={styles.section}>
            <span className={styles.stepBadge}>3</span>
            <div className={styles.sectionBody}>
              <h2 className={styles.sectionTitle}>Enter your email address</h2>
              <p className={styles.sectionDesc}>
                We&apos;ll notify you when we find an opening.
              </p>

              <div className={styles.fieldLabel}>
                <span>Where should we send notifications?*</span>
              </div>

              <input
                className={styles.emailInput}
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />

              <p className={styles.consent}>
                We&apos;ll create a free account when you submit this request —
                no password and no credit card needed. Already have an account?{" "}
                <Link href="/login" className={styles.consentLink}>
                  Log in
                </Link>
                .
              </p>
            </div>
          </section>

          <div className={styles.submitRow}>
            <button
              type="submit"
              className={styles.submitButton}
              disabled={!canSubmit || isSubmitting}
            >
              {isSubmitting ? "Creating alert…" : "Create alert"}
            </button>
            <p className={styles.terms}>
              By submitting this request, you agree to our{" "}
              <Link href="/terms" className={styles.consentLink}>
                Terms and Conditions
              </Link>
              .
            </p>
          </div>
        </form>
      )}
    </main>
  );
}
