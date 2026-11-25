"use client";

import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import styles from "./AtesInfo.module.css";

export const AVALANCHE_CANADA_URL = "https://avalanche.ca";
export const ATES_INFO_URL = "https://parks.canada.ca/pn-np/mtn/securiteenmontagne-mountainsafety/avalanche/echelle-ratings";

/**
 * What "Simple terrain" means, opened by a small info button (click or tap,
 * not hover, so it works on phones). Simple still has some avalanche
 * exposure; trails without an official rating are never counted as Simple.
 */
export default function AtesInfo({ label = "What is Simple terrain?" }: { label?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const box = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <span className={styles.wrap} ref={box}>
      <button
        type="button"
        className={styles.button}
        aria-expanded={open}
        aria-controls={id}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
      >
        <Info size={16} aria-hidden="true" />
      </button>
      {open && (
        <span id={id} role="note" className={styles.tip}>
          Simple (ATES class 1) is the lowest official rating for avalanche terrain, but it still has some
          exposure: short slopes or runouts from paths above. Trails with no official rating are never included.
          Always read the{" "}
          <a href={AVALANCHE_CANADA_URL} target="_blank" rel="noopener noreferrer">
            Avalanche Canada forecast
          </a>{" "}
          before you go, and see{" "}
          <a href={ATES_INFO_URL} target="_blank" rel="noopener noreferrer">
            Parks Canada&rsquo;s explanation of the ATES classes
          </a>
          .
        </span>
      )}
    </span>
  );
}
