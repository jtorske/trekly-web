"use client";

import { useId } from "react";
import { BADGE_SIZE, badgeOutline, nameFontSize, namePath } from "@/lib/badge";
import { homeLabel, type Province } from "@/lib/provinces";
import styles from "./ProvinceBadge.module.css";

const NAME_RADIUS = 41;
const C = BADGE_SIZE / 2;

/**
 * A home province or territory badge, in the Trail Journal badge style: a
 * round patch in the province's colour with a dashed inner ring, its motif
 * in cream on the centre disc, its name around the edge and its two-letter
 * code at the foot (Outside Canada has its own label and mark instead).
 *
 * With `decorative` it's hidden from screen readers (for use beside text
 * that already names the province).
 */
export default function ProvinceBadge({
  province,
  decorative = false,
  className = "",
}: {
  province: Province;
  decorative?: boolean;
  className?: string;
}) {
  const id = useId().replace(/:/g, "");
  const name = (province.badgeName ?? province.name).toUpperCase();
  const fontSize = nameFontSize(name, NAME_RADIUS);
  const label = decorative
    ? { "aria-hidden": true as const }
    : { role: "img", "aria-label": `${homeLabel(province)}: ${province.name} (badge showing ${province.motif})` };

  return (
    <svg
      viewBox={`0 0 ${BADGE_SIZE} ${BADGE_SIZE}`}
      className={`${styles.badge} ${className}`}
      style={{ "--badge": province.colour } as React.CSSProperties}
      data-province={province.code}
      {...label}
    >
      <defs>
        <path id={`${id}-name`} d={namePath(NAME_RADIUS)} />
        <clipPath id={`${id}-centre`}>
          <circle cx={C} cy={C} r={29} />
        </clipPath>
      </defs>
      <path d={badgeOutline("easy")} className={styles.patch} />
      <path d={badgeOutline("easy", 51)} className={styles.innerRing} />
      <circle cx={C} cy={C} r={29} className={styles.centre} />
      <g clipPath={`url(#${id}-centre)`}>
        {province.shapes.map((shape, index) => (
          <path
            key={index}
            d={shape.d}
            className={styles[shape.layer]}
            style={shape.width ? { strokeWidth: shape.width } : undefined}
          />
        ))}
      </g>
      <text className={styles.name} style={{ fontSize }}>
        <textPath href={`#${id}-name`} startOffset="50%" textAnchor="middle">
          {name}
        </textPath>
      </text>
      <text x={C} y={C + 43} className={styles.code} textAnchor="middle">
        {province.badgeFoot ?? province.code}
      </text>
    </svg>
  );
}
