"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
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
            Find backpacking routes by duration and location. Log your gear,
            and get a calculated packing plan for your trip.
          </p>

          <form className={styles.searchForm} action="/trails" method="get">
            <input
              className={styles.searchInput}
              type="search"
              name="q"
              placeholder="Where do you want to backpack?"
              aria-label="Search for a city or park"
            />
            <button className={styles.searchButton} type="submit">
              Search
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
