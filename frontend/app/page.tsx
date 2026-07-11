"use client";

import { useEffect, useRef, useState } from "react";

const backdropImages = [
  "/images/IMG_9031.jpeg",
  "/images/IMG_9023.jpeg",
  "/images/IMG_8988.jpeg",
  "/images/IMG_8883.jpeg",
  "/images/IMG_8873.jpeg",
];

const slideDurationMs = 6000;
const fadeDurationMs = 950;

export default function Home() {
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
    <main className="relative flex-1 overflow-hidden">
      <div className="absolute inset-0">
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-cover bg-center bg-no-repeat opacity-100"
          style={{ backgroundImage: `url(${backdropImages[activeIndex]})` }}
        />

        {incomingIndex !== null && (
          <div
            aria-hidden="true"
            className={`absolute inset-0 bg-cover bg-center bg-no-repeat transition-opacity duration-[950ms] ease-in-out ${
              incomingVisible ? "opacity-100" : "opacity-0"
            }`}
            style={{ backgroundImage: `url(${backdropImages[incomingIndex]})` }}
          />
        )}
      </div>

      <div className="absolute inset-0 bg-black/25" />
      <div className="absolute inset-0 bg-[linear-gradient(to_bottom,rgba(8,15,28,0.18),rgba(8,15,28,0.48))]" />

      <section className="relative z-10 flex min-h-full items-center justify-center px-8 py-16 text-center text-white">
        <div className="max-w-4xl">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-white/80">
            TrailQ
          </p>

          <h1 className="mt-4 text-5xl font-bold tracking-tight sm:text-6xl">
            Your next trail is waiting
          </h1>

          <p className="mx-auto mt-5 max-w-2xl text-lg text-white/85 sm:text-xl">
            Planning your journey begins here.
          </p>

          <button className="mt-10 rounded-full bg-white px-7 py-3 font-semibold text-slate-950 shadow-lg shadow-black/20 transition-transform hover:scale-[1.02]">
            Explore Trails
          </button>
        </div>
      </section>
    </main>
  );
}
