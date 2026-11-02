"use client";

import { useEffect, useId, useRef, useState, type Ref } from "react";
import Link from "next/link";
import SaveTrailButton from "@/components/SaveTrailButton";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { exploreHref } from "@/lib/exploreFilters";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { photoCredit } from "@/lib/trailPhoto";
import type { TrailPhoto as Photo, TrailSearchItem } from "@/lib/trailsApi";
import { tripLengthLabel } from "@/lib/tripLength";
import { formatTrailDistance, formatTrailElevation, formatWholeDistance, type UnitSystem } from "@/lib/units";
import styles from "./page.module.css";

/** "Banff National Park, AB": the park links to Explore filtered to it. */
function TrailPlace({ trail }: { trail: TrailSearchItem }) {
  const park = trail.park_name;
  if (!park) return <>{trail.region}</>;
  const link = (
    <Link href={exploreHref({ parks: [park] })} className={styles.parkLink}>
      {park}
    </Link>
  );
  const match = trail.region.match(/^(.*?)(,\s*[A-Z]{2})?$/);
  if (match && match[1] === park) {
    return (
      <>
        {link}
        {match[2] ?? ""}
      </>
    );
  }
  return (
    <>
      {trail.region} · {link}
    </>
  );
}

/**
 * The photo credit as a small ⓘ in the photo's corner: "Photo: name,
 * licence" shows on hover, keyboard focus or a tap, and links to the source.
 * The trail page keeps the full credit line.
 */
function PhotoInfo({ photo }: { photo: Photo }) {
  const [open, setOpen] = useState(false);
  const tipId = useId();
  const ref = useRef<HTMLSpanElement>(null);
  const credit = photoCredit(photo);

  // A tap elsewhere closes a tapped-open credit.
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  return (
    <span
      ref={ref}
      className={styles.photoInfo}
      data-open={open || undefined}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        className={styles.photoInfoButton}
        aria-label="Photo credit"
        aria-expanded={open}
        aria-controls={tipId}
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M8 7.2v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="8" cy="4.8" r="0.95" fill="currentColor" />
        </svg>
      </button>
      <span id={tipId} className={styles.photoTip}>
        {credit.href ? (
          <a href={credit.href} title={credit.title ?? undefined} target="_blank" rel="noopener noreferrer">
            {credit.text}
          </a>
        ) : (
          credit.text
        )}
      </span>
    </span>
  );
}

export function TrailCardSkeleton() {
  return (
    <li className={styles.cardItem} aria-hidden="true">
      <div className={`${styles.card} ${styles.skeletonCard}`}>
        <div className={`${styles.cardPhoto} ${ui.skeleton}`} />
        <div className={styles.cardBody}>
          <div className={styles.cardMain}>
            <div className={`${ui.skeleton} ${styles.skeletonTitle}`} />
            <div className={`${ui.skeleton} ${styles.skeletonLine}`} />
            <div className={`${ui.skeleton} ${styles.skeletonMeta}`} />
          </div>
        </div>
      </div>
    </li>
  );
}

interface TrailCardProps {
  trail: TrailSearchItem;
  title: string;
  saved: boolean;
  pending: boolean;
  onToggleSave: (trailId: string, makeSaved: boolean) => Promise<void>;
  returnTo: string;
  units: UnitSystem;
  /** Picked on the map. */
  selected: boolean;
  onHover: (id: string | null) => void;
  ref?: Ref<HTMLLIElement>;
}

export default function TrailCard({
  trail,
  title,
  saved,
  pending,
  onToggleSave,
  returnTo,
  units,
  selected,
  onHover,
  ref,
}: TrailCardProps) {
  const distance = formatTrailDistance(trail.distance_km, trail.route_type, units);
  const gain = formatTrailElevation(trail.elevation_gain_m, units);
  const meta = [
    trail.typical_duration_nights != null ? tripLengthLabel(trail.typical_duration_nights) : null,
    distance,
    gain ? `${gain} gain` : null,
    trail.distance_away_km != null ? `${formatWholeDistance(trail.distance_away_km, units)} away` : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <li
      ref={ref}
      className={styles.cardItem}
      data-selected={selected || undefined}
      onMouseEnter={() => onHover(trail.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(trail.id)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) onHover(null);
      }}
    >
      {/* The title's link covers the whole card; the park link, the save
          button and the photo credit sit above it. */}
      <div className={styles.card}>
        <div className={styles.cardPhoto}>
          <TrailPhoto photo={trail.photo} name={trail.name} variant="thumb" />
          {trail.photo && <PhotoInfo photo={trail.photo} />}
        </div>
        <div className={styles.cardBody}>
          <div className={styles.cardMain}>
            <h2 className={styles.cardName}>
              <Link href={`/trails?id=${encodeURIComponent(trail.id)}`} className={styles.cardLink}>
                {title}
              </Link>
            </h2>
            <p className={styles.cardRegion}>
              <TrailPlace trail={trail} />
            </p>
            <p className={styles.cardMeta}>
              <span className={`${styles.terrainTag} ${styles[trail.terrain]}`}>{TERRAIN_LABELS[trail.terrain]}</span>
              {meta.map((item) => (
                <span key={item} className={styles.metaItem}>
                  {item}
                </span>
              ))}
            </p>
          </div>
          <div className={styles.cardSave}>
            <SaveTrailButton
              trailId={trail.id}
              trailName={trail.name}
              saved={saved}
              pending={pending}
              onToggle={onToggleSave}
              returnTo={returnTo}
              compact
            />
          </div>
        </div>
      </div>
    </li>
  );
}
