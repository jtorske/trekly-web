"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Image from "next/image";
import type { LandingPhoto } from "@/lib/landingPhotos";
import { createHeroRotation, type HeroRotation } from "@/lib/heroRotation";
import RememberPhoto from "./RememberPhoto";
import styles from "./page.module.css";

/** Matches the .slide opacity transition in page.module.css. */
const FADE_MS = 1200;

/**
 * The landing hero's backdrop. It opens on the photo the server picked for
 * this visit (the page's LCP image), then crossfades through the rest of the
 * pool, loading only the next photo shortly before its turn. It holds still
 * while the tab is hidden and never moves under prefers-reduced-motion.
 */
export default function HeroCarousel({
  photos,
  start,
  children,
}: {
  photos: LandingPhoto[];
  start: number;
  children: ReactNode;
}) {
  const [shown, setShown] = useState(start);
  const [incoming, setIncoming] = useState<number | null>(null);
  const [leaving, setLeaving] = useState<number | null>(null);
  const rotation = useRef<HeroRotation | null>(null);
  const shownRef = useRef(start);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (motion.matches || photos.length < 2) return;

    let fadeTimer: number | undefined;
    const r = createHeroRotation({
      count: photos.length,
      start,
      onPreload: (index) => setIncoming(index),
      onShow: (index) => {
        setLeaving(shownRef.current);
        shownRef.current = index;
        setShown(index);
        setIncoming(null);
        window.clearTimeout(fadeTimer);
        fadeTimer = window.setTimeout(() => setLeaving(null), FADE_MS);
      },
    });
    rotation.current = r;

    const sync = () => {
      if (document.visibilityState === "visible" && !motion.matches) r.play();
      else r.pause();
    };
    sync();
    document.addEventListener("visibilitychange", sync);
    motion.addEventListener("change", sync);
    return () => {
      r.pause();
      rotation.current = null;
      window.clearTimeout(fadeTimer);
      document.removeEventListener("visibilitychange", sync);
      motion.removeEventListener("change", sync);
    };
  }, [photos, start]);

  // Below: the photo fading out. On top: the one on show (fading in when it
  // has just arrived). Mounted but invisible: the next one, loading.
  const slides = [leaving, shown, incoming].filter(
    (index, i, all): index is number => index !== null && all.indexOf(index) === i,
  );
  const credit = photos[shown].credit;

  return (
    <>
      <div className={styles.backdropContainer}>
        {slides.map((index) => {
          const photo = photos[index];
          const isStart = index === start;
          const state =
            index === shown ? styles.slideShown : index === leaving ? styles.slideLeaving : "";
          return (
            <Image
              key={photo.src}
              src={photo.src}
              alt=""
              aria-hidden="true"
              fill
              sizes="100vw"
              // Only the server's pick is the LCP image; the rest load one at
              // a time, when it's nearly their turn.
              {...(isStart ? { preload: true } : { loading: "eager" as const })}
              className={`${styles.backdrop} ${styles.slide} ${state}`}
              style={photo.position ? { objectPosition: photo.position } : undefined}
              data-hero-slide={index === shown ? "shown" : index === leaving ? "leaving" : "next"}
              onLoad={index === incoming ? () => rotation.current?.loaded(index) : undefined}
            />
          );
        })}
      </div>
      <RememberPhoto src={photos[shown].src} />

      {children}

      {credit && (
        <p className={styles.credit}>
          {credit.href ? (
            <a href={credit.href} target="_blank" rel="noopener noreferrer">
              {credit.text}
            </a>
          ) : (
            credit.text
          )}
        </p>
      )}
    </>
  );
}
