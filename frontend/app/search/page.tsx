"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Search as SearchIcon, UserRound } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import HikerRow from "@/components/social/HikerRow";
import ui from "@/components/ui.module.css";
import TrailCard, { TrailCardSkeleton } from "@/app/trail-list/TrailCard";
import trailStyles from "@/app/trail-list/page.module.css";
import { ApiError } from "@/lib/api";
import { nextQuery } from "@/lib/authLogic";
import { exploreHref } from "@/lib/exploreFilters";
import {
  MAX_QUERY,
  MIN_QUERY,
  SEARCH_DEBOUNCE_MS,
  SEARCH_TABS,
  TAB_STORAGE_KEY,
  initialTab,
  isSearchable,
  searchHref,
  searchTerm,
  type HikerPage,
  type SearchTab,
} from "@/lib/hikerSearch";
import { searchHikers } from "@/lib/hikerSearchApi";
import { trailTitles } from "@/lib/trailOrder";
import { searchExplore, type TrailSearchItem } from "@/lib/trailsApi";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { useUnits } from "@/lib/useUnits";
import styles from "./search.module.css";

const TRAIL_LIMIT = 24;

function remembered(): string | null {
  try {
    return window.localStorage.getItem(TAB_STORAGE_KEY);
  } catch {
    return null;
  }
}

function remember(tab: SearchTab) {
  try {
    window.localStorage.setItem(TAB_STORAGE_KEY, tab);
  } catch {
    // Private mode or blocked storage: the tab just isn't remembered.
  }
}

const isAbort = (error: unknown) => (error as { name?: string }).name === "AbortError";

/** Trails tab: Explore's own search, as cards. */
function TrailResults({ q }: { q: string }) {
  const term = q.trim();
  const [result, setResult] = useState<{ q: string; trails: TrailSearchItem[]; total: number } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const savedTrails = useSavedTrails();
  const [units] = useUnits();
  const returnTo = searchHref("trails", term);

  useEffect(() => {
    if (!term) return;
    const controller = new AbortController();
    searchExplore({ q: term, limit: TRAIL_LIMIT }, controller.signal)
      .then((found) => {
        setResult({ q: term, trails: found.trails, total: found.total });
        setFailed(null);
      })
      .catch((error: unknown) => {
        if (!isAbort(error)) setFailed(term);
      });
    return () => controller.abort();
  }, [term, attempt]);

  const trails = useMemo(() => result?.trails ?? [], [result]);
  const titles = useMemo(() => trailTitles(trails), [trails]);

  if (!term) {
    return (
      <div className={styles.hint}>
        <p>Search trails by name, park or region.</p>
        <Link href="/trail-list" className={ui.secondary}>
          Browse trails on Explore
        </Link>
      </div>
    );
  }
  if (failed === term) {
    return (
      <div className={styles.hint} role="alert">
        <p>We couldn&apos;t search trails just now.</p>
        <button type="button" className={ui.secondary} onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  const loading = result?.q !== term;
  if (!result) {
    return (
      <ul className={trailStyles.list} aria-busy="true" aria-label="Loading trails">
        {[0, 1, 2].map((n) => (
          <TrailCardSkeleton key={n} />
        ))}
      </ul>
    );
  }
  if (result.trails.length === 0) {
    return (
      <p className={`${styles.hint} ${loading ? trailStyles.stale : ""}`}>
        No trails match &ldquo;{result.q}&rdquo;. Try a park or region instead.
      </p>
    );
  }
  return (
    <>
      <p className={styles.count} aria-live="polite">
        {result.total.toLocaleString("en-CA")} {result.total === 1 ? "trail" : "trails"}
      </p>
      <ul className={`${trailStyles.list} ${loading ? trailStyles.stale : ""}`}>
        {result.trails.map((trail) => (
          <TrailCard
            key={trail.id}
            trail={trail}
            title={titles.get(trail.id) ?? trail.name}
            saved={savedTrails.savedIds.has(trail.id)}
            pending={savedTrails.pending.has(trail.id)}
            onToggleSave={savedTrails.toggle}
            returnTo={returnTo}
            units={units}
            selected={false}
            onHover={() => {}}
          />
        ))}
      </ul>
      {result.total > result.trails.length && (
        <div className={styles.more}>
          <Link href={exploreHref({ q: result.q })} className={ui.secondary}>
            See all {result.total.toLocaleString("en-CA")} on Explore
          </Link>
        </div>
      )}
    </>
  );
}

/** Hikers tab: people search, signed in only. */
function HikerResults({ q }: { q: string }) {
  const { status } = useAuth();
  const pathname = usePathname();
  const term = searchTerm(q);
  const searchable = isSearchable(q);
  const [pages, setPages] = useState<{ q: string; page: HikerPage } | null>(null);
  const [error, setError] = useState<{ q: string; message: string } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const signedIn = status === "signedIn";

  useEffect(() => {
    if (!signedIn || !searchable) return;
    const controller = new AbortController();
    searchHikers(term, { signal: controller.signal })
      .then((page) => {
        setPages({ q: term, page });
        setError(null);
      })
      .catch((caught: unknown) => {
        if (isAbort(caught)) return;
        setError({ q: term, message: caught instanceof ApiError ? caught.message : "We couldn't search just now." });
      });
    return () => controller.abort();
  }, [signedIn, searchable, term, attempt]);

  const loadMore = async () => {
    if (!pages?.page.next_offset) return;
    setLoadingMore(true);
    try {
      const next = await searchHikers(pages.q, { offset: pages.page.next_offset });
      setPages((current) =>
        current && current.q === pages.q
          ? { q: current.q, page: { items: [...current.page.items, ...next.items], next_offset: next.next_offset } }
          : current,
      );
    } catch (caught) {
      setError({ q: pages.q, message: caught instanceof ApiError ? caught.message : "We couldn't load more just now." });
    } finally {
      setLoadingMore(false);
    }
  };

  if (status === "loading") return <div className={`${ui.skeleton} ${styles.rowSkeleton}`} />;
  if (!signedIn) {
    return (
      <div className={styles.hint}>
        <UserRound size={28} aria-hidden="true" className={styles.hintIcon} />
        <p>Sign in to find other hikers and follow them.</p>
        <div className={styles.hintActions}>
          <Link href={`/login${nextQuery(`${pathname}?tab=hikers`)}`} className={ui.primary}>
            Sign in
          </Link>
          <Link href="/signup" className={ui.secondary}>
            Create an account
          </Link>
        </div>
      </div>
    );
  }
  if (!searchable) {
    return (
      <p className={styles.hint}>
        {term ? `Type at least ${MIN_QUERY} characters.` : "Search for hikers by name or username."}
      </p>
    );
  }
  if (error?.q === term && pages?.q !== term) {
    return (
      <div className={styles.hint} role="alert">
        <p>{error.message}</p>
        <button type="button" className={ui.secondary} onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  if (!pages) {
    return (
      <div aria-busy="true" aria-label="Loading hikers">
        {[0, 1, 2].map((n) => (
          <div key={n} className={`${ui.skeleton} ${styles.rowSkeleton}`} />
        ))}
      </div>
    );
  }
  const stale = pages.q !== term;
  if (pages.page.items.length === 0) {
    return (
      <div className={`${styles.hint} ${stale ? trailStyles.stale : ""}`}>
        <p>No hikers match &ldquo;{pages.q}&rdquo;.</p>
        <p className={styles.small}>Private profiles only appear if their owner lets people find them.</p>
      </div>
    );
  }
  return (
    <>
      <ul className={`${styles.people} ${stale ? trailStyles.stale : ""}`} aria-label="Hikers">
        {pages.page.items.map((hiker) => (
          <HikerRow key={hiker.username} hiker={hiker} />
        ))}
      </ul>
      {error?.q === pages.q && (
        <p className={ui.error} role="alert">
          {error.message}
        </p>
      )}
      {pages.page.next_offset !== null && !stale && (
        <div className={styles.more}>
          <button type="button" className={ui.secondary} onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Show more"}
          </button>
        </div>
      )}
    </>
  );
}

function SearchPage() {
  const params = useSearchParams();
  const [tab, setTab] = useState<SearchTab>(() =>
    initialTab(params.get("tab"), typeof window === "undefined" ? null : remembered()),
  );
  const [query, setQuery] = useState(() => params.get("q") ?? "");
  const q = useDebouncedValue(query, SEARCH_DEBOUNCE_MS);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Keep the URL shareable without adding history entries per keystroke.
  useEffect(() => {
    window.history.replaceState(null, "", searchHref(tab, q));
  }, [tab, q]);

  // The tab shown is the tab used, whether picked here or linked to.
  useEffect(() => remember(tab), [tab]);

  const choose = useCallback((next: SearchTab) => {
    setTab(next);
    inputRef.current?.focus();
  }, []);

  return (
    <main className={styles.page}>
      <div className={styles.inner}>
        <h1 className={styles.title}>Search</h1>
        <form className={styles.bar} role="search" onSubmit={(event) => event.preventDefault()}>
          <SearchIcon size={18} aria-hidden="true" className={styles.barIcon} />
          <label htmlFor="site-search" className={ui.srOnly}>
            {tab === "hikers" ? "Search hikers by name or username" : "Search trails"}
          </label>
          <input
            ref={inputRef}
            id="site-search"
            type="search"
            className={styles.input}
            placeholder={tab === "hikers" ? "Name or @username" : "Trail, park or region"}
            value={query}
            maxLength={MAX_QUERY}
            autoComplete="off"
            enterKeyHint="search"
            onChange={(event) => setQuery(event.target.value)}
          />
        </form>

        <div className={styles.tabs} role="tablist" aria-label="Search for">
          {SEARCH_TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              id={`search-tab-${item.key}`}
              aria-selected={tab === item.key}
              aria-controls="search-panel"
              className={styles.tab}
              onClick={() => choose(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <section id="search-panel" role="tabpanel" aria-labelledby={`search-tab-${tab}`} className={styles.panel}>
          {tab === "hikers" ? <HikerResults q={q} /> : <TrailResults q={q} />}
        </section>
      </div>
    </main>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <SearchPage />
    </Suspense>
  );
}
