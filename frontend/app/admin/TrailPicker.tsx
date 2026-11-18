"use client";

import { useEffect, useId, useState } from "react";
import { Search, X } from "lucide-react";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import styles from "./admin.module.css";
import page from "./posts/page.module.css";

/** Pick a trail by name; one at a time. */
export default function TrailPicker({
  trail,
  onChange,
  label = "Link a trail (optional)",
}: {
  trail: TrailListItem | null;
  onChange: (t: TrailListItem | null) => void;
  label?: string;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ query: string; trails: TrailListItem[] } | null>(null);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchTrails(term, controller.signal, { limit: 6 })
        .then((trails) => setResults({ query: term, trails }))
        .catch(() => undefined);
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  if (trail) {
    return (
      <div className={page.chosenTrail}>
        <span className={page.trailThumb}>
          <TrailPhoto photo={trail.photo} routeMap={trail.route_map} name={trail.name} variant="thumb" mini />
        </span>
        <span className={page.trailName}>
          {trail.name}
          <span className={styles.muted}> · {trail.park_name ?? trail.region}</span>
        </span>
        <button type="button" className={ui.ghost} onClick={() => onChange(null)} aria-label={`Remove ${trail.name}`}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    );
  }
  const shown = results && results.query === query.trim() ? results.trails : [];
  return (
    <div className={page.picker}>
      <label htmlFor={id} className={ui.srOnly}>
        {label}
      </label>
      <span className={page.searchBox}>
        <Search size={16} aria-hidden="true" />
        <input
          id={id}
          className={ui.input}
          type="search"
          placeholder={label}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
      </span>
      {shown.length > 0 && (
        <ul className={page.results}>
          {shown.map((option) => (
            <li key={option.id}>
              <button
                type="button"
                className={page.result}
                onClick={() => {
                  onChange(option);
                  setQuery("");
                }}
              >
                <span className={page.trailThumb}>
                  <TrailPhoto photo={option.photo} routeMap={option.route_map} name={option.name} variant="thumb" mini />
                </span>
                <span>
                  {option.name}
                  <span className={styles.muted}> · {option.park_name ?? option.region}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
