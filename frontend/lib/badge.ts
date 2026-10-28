import type { Terrain } from "./terrain";

/**
 * Geometry for the Trail Journal badges, generated from trail data rather
 * than drawn by hand. All shapes are roughly round so the name can run
 * around a circle inside any of them:
 *
 *   easy → circle, moderate → hexagon, difficult → scalloped seal,
 *   extreme → sixteen-point starburst.
 */

export const BADGE_SIZE = 120;
const C = BADGE_SIZE / 2;

const round = (n: number) => Math.round(n * 100) / 100;

function polygon(points: [number, number][]): string {
  return `M${points.map(([x, y]) => `${round(x)} ${round(y)}`).join("L")}Z`;
}

function polar(radius: number, angle: number): [number, number] {
  return [C + radius * Math.cos(angle), C + radius * Math.sin(angle)];
}

/** The badge's outer edge as a path, centred in a BADGE_SIZE square. */
export function badgeOutline(terrain: Terrain, radius = 56): string {
  switch (terrain) {
    case "easy":
      return `M${C - radius} ${C}a${radius} ${radius} 0 1 0 ${radius * 2} 0a${radius} ${radius} 0 1 0 ${-radius * 2} 0Z`;
    case "moderate":
      return polygon(Array.from({ length: 6 }, (_, i) => polar(radius, (Math.PI / 3) * i - Math.PI / 2)));
    case "difficult": {
      // 12 scallops: each edge bulges outward as a quadratic curve.
      const n = 12;
      const inner = radius * 0.93;
      let d = "";
      for (let i = 0; i < n; i++) {
        const a0 = ((Math.PI * 2) / n) * i - Math.PI / 2;
        const a1 = a0 + (Math.PI * 2) / n;
        const [x0, y0] = polar(inner, a0);
        const [cx, cy] = polar(radius * 1.07, (a0 + a1) / 2);
        const [x1, y1] = polar(inner, a1);
        d += `${i === 0 ? `M${round(x0)} ${round(y0)}` : ""}Q${round(cx)} ${round(cy)} ${round(x1)} ${round(y1)}`;
      }
      return `${d}Z`;
    }
    case "extreme": {
      const points: [number, number][] = [];
      for (let i = 0; i < 32; i++) {
        points.push(polar(i % 2 ? radius * 0.86 : radius, (Math.PI / 16) * i - Math.PI / 2));
      }
      return polygon(points);
    }
  }
}

/**
 * The circle the name runs along: from the lower left, clockwise over the
 * top, to the lower right, so the text reads upright.
 */
export function namePath(radius: number): string {
  const [x0, y0] = polar(radius, (Math.PI * 3) / 4);
  const [x1, y1] = polar(radius, Math.PI / 4);
  return `M${round(x0)} ${round(y0)}A${radius} ${radius} 0 1 1 ${round(x1)} ${round(y1)}`;
}

/** Arc length of namePath: three quarters of the circle. */
export const nameArcLength = (radius: number) => radius * Math.PI * 1.5;

/**
 * A font size that fits `name` on the arc (DM Sans caps average about 0.68em
 * per character including letter-spacing), capped for short names.
 */
export function nameFontSize(name: string, radius: number, max = 9.5, min = 5.5): number {
  const fit = (nameArcLength(radius) * 0.92) / (Math.max(name.length, 1) * 0.68);
  return round(Math.max(min, Math.min(max, fit)));
}

/**
 * An elevation profile (metres, in order along the route) as a filled
 * mountain silhouette inside `box` = [x, y, width, height]. Needs at least
 * two points; returns null otherwise so the badge falls back to its icon.
 */
export function profileSilhouette(profile: number[] | null | undefined, box: [number, number, number, number]): string | null {
  const points = (profile ?? []).filter((value) => Number.isFinite(value));
  if (points.length < 2) return null;
  const [x, y, width, height] = box;
  const low = Math.min(...points);
  const span = Math.max(...points) - low || 1;
  const step = width / (points.length - 1);
  const line = points.map((value, i) => `${round(x + i * step)} ${round(y + height - ((value - low) / span) * height * 0.85)}`);
  return `M${x} ${y + height}L${line.join("L")}L${x + width} ${y + height}Z`;
}

/** Line icons for the milestone medals (Trail Journal and profile), in a 120 square. */
export const MILESTONE_ICONS = {
  "first-hike": "M26 80 52 46l10 12 8-10 24 32M60 54V28l16 6-16 6",
  "first-overnight": "M30 76 60 34l30 42Zm30-42v42M74 30a8 8 0 1 1-8-10 6 6 0 0 0 8 10Z",
  "five-parks": "M26 76l16-26 10 14 12-22 20 34Z",
  "hundred-km": "M28 70c10-24 24-6 32-20s16-16 32-8",
} as const;
