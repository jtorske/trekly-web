"use client";

import { useEffect, useId, useMemo, useState } from "react";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { mergeTrails, orderForPicker, searchPicker, type PickerPreferences } from "@/lib/pastHikes";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import styles from "./PastHikesPicker.module.css";

/**
 * "Which of these have you hiked?": trail cards to tap, with search. The
 * parent owns the selection and saves it (onboarding's /welcome step and
 * the journal's "Add past hikes" dialog both use this). Trails already in
 * the journal show as such and can't be picked again.
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
  const [remote, setRemote] = useState<{ query: string; trails: TrailListItem[] } | null>(null);
  const ordered = useMemo(() => orderForPicker(catalogue, preferences), [catalogue, preferences]);
  const local = useMemo(() => searchPicker(ordered, query), [ordered, query]);

  // The picker lists the most popular trails; a search also asks the server,
  // so less popular ones can still be found.
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
  const shown = remote && remote.query === trimmed && trimmed.length >= 2 ? mergeTrails(local, remote.trails) : local;

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

      {shown.length === 0 ? (
        <p className={styles.empty}>No trails match &ldquo;{query}&rdquo;.</p>
      ) : (
        <ul className={styles.grid} aria-label="Trails">
          {shown.map((trail) => {
            const inJournal = logged.has(trail.id);
            const on = inJournal || selected.has(trail.id);
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
                  <span className={styles.park}>{inJournal ? "In your journal" : (trail.park_name ?? trail.region)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
