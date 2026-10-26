"use client";

import { useId } from "react";
import { BADGE_SIZE, badgeOutline, nameFontSize, namePath, profileSilhouette } from "@/lib/badge";
import { TERRAIN_LABELS, type Terrain } from "@/lib/terrain";
import styles from "./TrailBadge.module.css";

const NAME_RADIUS = 41;
const C = BADGE_SIZE / 2;

/**
 * A Trail Journal badge, generated from the trail's data: the outline from
 * its difficulty, the fill from its park or region, its name around the
 * edge and its elevation profile (or a mountain icon) in the middle.
 *
 * Not yet hiked, it's an empty dashed slot with just the name. `stamp`
 * plays the stamp-in animation once (the caller decides when it's new).
 */
export default function TrailBadge({
  name,
  terrain,
  colour,
  hiked,
  profile,
  stamp = false,
  onStamped,
  className = "",
}: {
  name: string;
  terrain: Terrain;
  colour: string;
  hiked: boolean;
  profile?: number[] | null;
  stamp?: boolean;
  onStamped?: () => void;
  className?: string;
}) {
  const id = useId().replace(/:/g, "");
  const outline = badgeOutline(terrain);
  const fontSize = nameFontSize(name.toUpperCase(), NAME_RADIUS);
  const silhouette = profileSilhouette(profile, [C - 24, C - 14, 48, 30]);

  return (
    <svg
      viewBox={`0 0 ${BADGE_SIZE} ${BADGE_SIZE}`}
      className={`${styles.badge} ${hiked ? styles.hiked : styles.locked} ${stamp ? styles.stamp : ""} ${className}`}
      style={{ "--badge": colour } as React.CSSProperties}
      role="img"
      aria-label={`${name}, ${TERRAIN_LABELS[terrain].toLowerCase()}${hiked ? ", hiked" : ", not hiked yet"}`}
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget) onStamped?.();
      }}
    >
      <defs>
        <path id={`${id}-name`} d={namePath(NAME_RADIUS)} />
        <clipPath id={`${id}-centre`}>
          <circle cx={C} cy={C} r={29} />
        </clipPath>
      </defs>

      {hiked ? (
        <>
          <path d={outline} className={styles.fill} />
          <path d={badgeOutline(terrain, 51)} className={styles.innerRing} />
          <circle cx={C} cy={C} r={29} className={styles.centre} />
          <g clipPath={`url(#${id}-centre)`}>
            {silhouette ? (
              <path d={silhouette} className={styles.mountain} />
            ) : (
              <>
                <path d={`M${C - 26} ${C + 16}L${C - 8} ${C - 8}L${C + 1} ${C + 2}L${C + 8} ${C - 14}L${C + 28} ${C + 16}Z`} className={styles.mountain} />
                <path d={`M${C + 8} ${C - 14}L${C + 3.5} ${C - 4}L${C + 7} ${C - 6}L${C + 10} ${C - 3}L${C + 12.5} ${C - 5}Z`} className={styles.snow} />
                <path d={`M${C - 8} ${C - 8}L${C - 12} ${C - 2}L${C - 8} ${C - 4}L${C - 5} ${C - 2}Z`} className={styles.snow} />
              </>
            )}
          </g>
          <text className={styles.name} style={{ fontSize }}>
            <textPath href={`#${id}-name`} startOffset="50%" textAnchor="middle">
              {name.toUpperCase()}
            </textPath>
          </text>
          <circle cx={C} cy={C + 40} r={2} className={styles.star} />
        </>
      ) : (
        <>
          <path d={outline} className={styles.slot} />
          <text className={styles.name} style={{ fontSize }}>
            <textPath href={`#${id}-name`} startOffset="50%" textAnchor="middle">
              {name.toUpperCase()}
            </textPath>
          </text>
        </>
      )}
    </svg>
  );
}
