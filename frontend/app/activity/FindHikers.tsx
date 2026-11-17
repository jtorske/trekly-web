"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search as SearchIcon } from "lucide-react";
import HikerRow from "@/components/social/HikerRow";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import {
  DROPDOWN_ROWS,
  MAX_QUERY,
  SEARCH_DEBOUNCE_MS,
  isSearchable,
  searchHref,
  searchTerm,
  type HikerPage,
} from "@/lib/hikerSearch";
import { searchHikers } from "@/lib/hikerSearchApi";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import styles from "./activity.module.css";

/**
 * "Find hikers" in the Activity sidebar: results drop down under the box as
 * you type (the first few), with "See all results" for /search. Enter goes
 * to the full results; Escape or a click elsewhere closes the dropdown.
 */
export default function FindHikers() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [found, setFound] = useState<{ q: string; page: HikerPage } | null>(null);
  const [error, setError] = useState<{ q: string; message: string } | null>(null);
  const q = useDebouncedValue(query, SEARCH_DEBOUNCE_MS);
  const term = searchTerm(q);
  const searchable = isSearchable(q);
  const rootRef = useRef<HTMLDivElement>(null);
  const resultsId = useId();

  useEffect(() => {
    if (!searchable) return;
    const controller = new AbortController();
    searchHikers(term, { limit: DROPDOWN_ROWS, signal: controller.signal })
      .then((page) => {
        setFound({ q: term, page });
        setError(null);
      })
      .catch((caught: unknown) => {
        if ((caught as { name?: string }).name === "AbortError") return;
        setError({ q: term, message: caught instanceof ApiError ? caught.message : "We couldn't search just now." });
      });
    return () => controller.abort();
  }, [searchable, term]);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const showing = open && isSearchable(query);
  const current = found?.q === term ? found : null;
  const failed = error?.q === term ? error.message : null;

  return (
    <section className={styles.sideCard} aria-labelledby="find-hikers-title">
      <h2 id="find-hikers-title" className={styles.sideTitle}>
        Find hikers
      </h2>
      <div
        ref={rootRef}
        className={styles.finder}
        onKeyDown={(event) => {
          if (event.key === "Escape" && open) {
            event.stopPropagation();
            setOpen(false);
          }
        }}
      >
        <form
          role="search"
          className={styles.finderBar}
          onSubmit={(event) => {
            event.preventDefault();
            if (isSearchable(query)) router.push(searchHref("hikers", searchTerm(query)));
          }}
        >
          <SearchIcon size={16} aria-hidden="true" className={styles.finderIcon} />
          <label htmlFor="find-hikers" className={ui.srOnly}>
            Find hikers by name or username
          </label>
          <input
            id="find-hikers"
            type="search"
            className={styles.finderInput}
            placeholder="Name or @username"
            value={query}
            maxLength={MAX_QUERY}
            autoComplete="off"
            enterKeyHint="search"
            aria-controls={showing ? resultsId : undefined}
            onFocus={() => setOpen(true)}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
          />
        </form>

        {showing && (
          <div id={resultsId} className={styles.finderResults} role="region" aria-label="Hikers found">
            {failed ? (
              <p className={styles.finderNote} role="alert">
                {failed}
              </p>
            ) : !current ? (
              <div aria-busy="true" aria-label="Searching">
                {[0, 1].map((n) => (
                  <div key={n} className={`${ui.skeleton} ${styles.finderSkeleton}`} />
                ))}
              </div>
            ) : current.page.items.length === 0 ? (
              <p className={styles.finderNote}>No hikers match &ldquo;{current.q}&rdquo;.</p>
            ) : (
              <ul className={styles.finderList}>
                {current.page.items.map((hiker) => (
                  <HikerRow key={hiker.username} hiker={hiker} compact onNavigate={() => setOpen(false)} />
                ))}
              </ul>
            )}
            <Link href={searchHref("hikers", searchTerm(query))} className={styles.finderAll} onClick={() => setOpen(false)}>
              See all results
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}
