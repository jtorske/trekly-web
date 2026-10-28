import { BADGE_SIZE, badgeOutline } from "@/lib/badge";
import type { Terrain } from "@/lib/terrain";
import styles from "./RankEmblem.module.css";

const C = BADGE_SIZE / 2;

/** Per level (1-7): the outline (as the trail badges draw them) and the fill. */
const LOOK: { shape: Terrain; fill: string }[] = [
  { shape: "easy", fill: "#7d8a5a" },
  { shape: "easy", fill: "#4a5e43" },
  { shape: "moderate", fill: "#2f5d62" },
  { shape: "moderate", fill: "#3d4f7a" },
  { shape: "difficult", fill: "#6b3f5a" },
  { shape: "difficult", fill: "#8a4a1c" },
  { shape: "extreme", fill: "#a8752c" },
];

/**
 * A rank's emblem, generated in the Trail Journal badges' style: the
 * outline grows bolder with each rank (circle, hexagon, seal, starburst),
 * with a mountain mark and one pip per level. Decorative unless `label`.
 */
export default function RankEmblem({ level, label, className = "" }: { level: number; label?: string; className?: string }) {
  const look = LOOK[Math.min(Math.max(level, 1), LOOK.length) - 1];
  const pips = Array.from({ length: level }, (_, i) => {
    // Spread along the bottom arc, centred.
    const angle = Math.PI / 2 + (i - (level - 1) / 2) * 0.24;
    return { x: C + 36 * Math.cos(angle), y: C + 36 * Math.sin(angle) };
  });
  return (
    <svg
      viewBox={`0 0 ${BADGE_SIZE} ${BADGE_SIZE}`}
      className={`${styles.emblem} ${className}`}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <path d={badgeOutline(look.shape)} fill={look.fill} className={styles.outline} />
      <circle cx={C} cy={C} r={42} className={styles.ring} />
      <path d="M32 72 50 44l9 12 9-15 20 31Z" className={styles.mountain} />
      <path d="M50 44l5 7-5 3-5-3Zm18-3 5 8-5 2-5-2Z" className={styles.snow} />
      {pips.map((pip, i) => (
        <circle key={i} cx={pip.x} cy={pip.y} r={3.2} className={styles.pip} />
      ))}
    </svg>
  );
}
