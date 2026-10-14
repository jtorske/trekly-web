"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useRouter } from "next/navigation";
import { TERRAIN_LABELS } from "@/app/packplanner/packingList";
import { searchTrails, type TrailSummary } from "@/lib/trailsApi";
import styles from "./page.module.css";

const backdropImages = [
  "/images/IMG_9031.jpeg",
  "/images/IMG_8988.jpeg",
  "/images/IMG_8873.jpeg",
  "/images/IMG_9332.jpeg",
  "/images/IMG_9336.jpeg",
  "/images/IMG_9627.jpg",
];

const slideDurationMs = 6000;
const fadeDurationMs = 950;

function TrailSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TrailSummary[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const trimmedQuery = query.trim();

  useEffect(() => {
    if (trimmedQuery.length < 2) return;

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setIsSearching(true);
      searchTrails(trimmedQuery, controller.signal)
        .then((trails) => {
          setResults(trails);
          setHighlightedIndex(-1);
        })
        .catch((error: unknown) => {
          if ((error as { name?: string }).name !== "AbortError") setResults([]);
        })
        .finally(() => setIsSearching(false));
    }, 300);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [trimmedQuery]);

  const showDropdown = isOpen && trimmedQuery.length >= 2;
  const showNoMatch = showDropdown && !isSearching && results.length === 0;
  const highlightedTrail = showDropdown ? results[highlightedIndex] : undefined;

  const openTrail = (trail: TrailSummary) => {
    setIsOpen(false);
    router.push(`/trails?id=${encodeURIComponent(trail.id)}`);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (highlightedTrail) {
      openTrail(highlightedTrail);
      return;
    }
    setIsOpen(false);
    router.push(
      trimmedQuery
        ? `/trail-list?q=${encodeURIComponent(trimmedQuery)}`
        : "/trail-list",
    );
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setIsOpen(false);
      setHighlightedIndex(-1);
      return;
    }
    if (!showDropdown || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((index) =>
        index <= 0 ? results.length - 1 : index - 1,
      );
    }
  };

  return (
    <div className={styles.searchWrap}>
      <form className={styles.searchForm} onSubmit={handleSubmit}>
        <input
          className={styles.searchInput}
          type="search"
          name="q"
          role="combobox"
          aria-expanded={showDropdown}
          aria-controls="landing-trail-results"
          aria-autocomplete="list"
          aria-activedescendant={
            highlightedTrail ? `landing-trail-${highlightedTrail.id}` : undefined
          }
          autoComplete="off"
          placeholder="Where do you want to backpack?"
          aria-label="Search for a trail or region"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setIsOpen(true);
            setHighlightedIndex(-1);
          }}
          onFocus={() => setIsOpen(true)}
          onBlur={() => setIsOpen(false)}
          onKeyDown={handleKeyDown}
        />
        <button className={styles.searchButton} type="submit">
          Search
        </button>
      </form>

      {showDropdown && (isSearching || results.length > 0 || showNoMatch) && (
        <ul
          id="landing-trail-results"
          role="listbox"
          className={styles.trailResults}
        >
          {isSearching && results.length === 0 && (
            <li className={styles.trailStatus}>Searching…</li>
          )}
          {results.map((trail, index) => (
            <li
              key={trail.id}
              id={`landing-trail-${trail.id}`}
              role="option"
              aria-selected={index === highlightedIndex}
            >
              <button
                type="button"
                tabIndex={-1}
                className={`${styles.trailOption} ${
                  index === highlightedIndex ? styles.trailOptionActive : ""
                }`}
                onMouseDown={(event) => {
                  event.preventDefault();
                  openTrail(trail);
                }}
                onMouseEnter={() => setHighlightedIndex(index)}
              >
                <span className={styles.trailOptionName}>
                  {trail.name}, {trail.region}
                </span>
                <span className={styles.trailOptionTerrain}>
                  {TERRAIN_LABELS[trail.terrain]}
                </span>
              </button>
            </li>
          ))}
          {showNoMatch && (
            <li className={styles.trailStatus}>
              No trails match yet. Press Enter to explore.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export default function LandingPage() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeIndexRef = useRef(0);
  const [incomingIndex, setIncomingIndex] = useState<number | null>(null);
  const [incomingVisible, setIncomingVisible] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let slideTimer: ReturnType<typeof setTimeout> | undefined;
    let transitionTimer: ReturnType<typeof setTimeout> | undefined;

    const preloadImage = (source: string) =>
      new Promise<boolean>((resolve) => {
        const image = new window.Image();
        image.onload = () => resolve(true);
        image.onerror = () => resolve(false);
        image.src = source;
      });

    const startCycle = () => {
      slideTimer = setTimeout(async () => {
        const upcomingIndex =
          (activeIndexRef.current + 1) % backdropImages.length;

        const loaded = await preloadImage(backdropImages[upcomingIndex]);

        if (cancelled || !loaded) {
          startCycle();
          return;
        }

        setIncomingIndex(upcomingIndex);

        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (cancelled) {
              return;
            }

            setIncomingVisible(true);

            transitionTimer = setTimeout(() => {
              if (cancelled) {
                return;
              }

              setActiveIndex(upcomingIndex);
              activeIndexRef.current = upcomingIndex;
              setIncomingIndex(null);
              setIncomingVisible(false);
              startCycle();
            }, fadeDurationMs);
          });
        });
      }, slideDurationMs);
    };

    startCycle();

    return () => {
      cancelled = true;

      if (slideTimer) {
        clearTimeout(slideTimer);
      }

      if (transitionTimer) {
        clearTimeout(transitionTimer);
      }
    };
  }, []);

  return (
    <main className={styles.hero}>
      <div className={styles.backdropContainer}>
        <div
          aria-hidden="true"
          className={styles.backdrop}
          style={{ backgroundImage: `url(${backdropImages[activeIndex]})` }}
        />

        {incomingIndex !== null && (
          <div
            aria-hidden="true"
            className={`${styles.backdrop} ${styles.incoming} ${
              incomingVisible ? styles.visible : styles.hidden
            }`}
            style={{ backgroundImage: `url(${backdropImages[incomingIndex]})` }}
          />
        )}
      </div>

      <div aria-hidden="true" className={styles.scrim} />

      <section className={styles.section}>
        <div className={styles.content}>
          <h1 className={styles.headline}>Your next trail is waiting</h1>

          <p className={styles.subtext}>
            Find backpacking routes by duration and location. Log your gear, and
            get a calculated packing plan for your trip.
          </p>

          <TrailSearch />
        </div>
      </section>
    </main>
  );
}
