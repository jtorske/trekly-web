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

/**
 * Line icons for the milestone medals (Trail Journal and profile), in a 120
 * square, keyed by the `icon` each milestone names in the backend's
 * app/milestones_config.py (a backend test checks every one is here).
 */
export const MILESTONE_ICONS: Record<string, string> = {
  "first-hike": "M26 80 52 46l10 12 8-10 24 32M60 54V28l16 6-16 6",
  "first-overnight": "M30 76 60 34l30 42Zm30-42v42M74 30a8 8 0 1 1-8-10 6 6 0 0 0 8 10Z",
  "five-parks": "M26 76l16-26 10 14 12-22 20 34Z",
  "hundred-km": "M28 70c10-24 24-6 32-20s16-16 32-8",
  boot: "M44 32h18v30l18 7a7 7 0 0 1 5 7v8H44ZM44 84h41M44 46h10",
  boots: "M30 36h14v26l14 6v12H30ZM62 42h14v26l14 6v12H62Z",
  blaze: "M48 92V26M72 92V26M54 46h12v14H54Z",
  repeat: "M84 60a24 24 0 1 1-7-17M84 30v14H70",
  "tent-moon": "M26 86 50 48l24 38ZM50 48v38M90 36a9 9 0 1 1-10-12 7 7 0 0 0 10 12Z",
  campfire: "M36 88l48-12M36 76l48 12M60 72c-10-6-8-18 0-28 2 9 11 11 8 20-1 5-4 8-8 8Z",
  moon: "M70 28a32 32 0 1 0 22 46 26 26 0 0 1-22-46Z",
  path: "M38 92c4-14 42-14 42-28s-36-12-36-26 18-12 18-12",
  compass: "M60 28a32 32 0 1 1 0 64 32 32 0 1 1 0-64ZM60 42l8 18-8 18-8-18Z",
  switchbacks: "M34 90h44L42 76h40L46 62h36L54 48h20M74 48V30",
  summit: "M22 86 50 44l10 12 14-24 24 54ZM68 38l6-6 6 6",
  flag: "M44 92V28M44 30h34l-8 10 8 10H44",
  peaks: "M16 84l12-20 9 11 11-25 10 17 11-27 12 24 8-10 15 30Z",
  passport: "M38 26h44v68H38ZM60 48a10 10 0 1 1 0 20 10 10 0 1 1 0-20ZM50 82h20",
  "north-star": "M60 24l7 29 29 7-29 7-7 29-7-29-29-7 29-7Z",
  waves: "M24 52c8-8 16-8 24 0s16 8 24 0 16-8 24 0M24 70c8-8 16-8 24 0s16 8 24 0 16-8 24 0",
  "check-map": "M26 36l22-8 24 8 22-8v56l-22 8-24-8-22 8ZM46 60l10 10 18-20",
  spectrum: "M34 86V72M50 86V60M66 86V48M82 86V34",
  pickaxe: "M38 86 74 50M54 34c16-6 30-2 38 10-12-4-24-2-34 6Z",
  starburst: "M60 24l8 22 22-8-8 22 22 8-22 8 8 22-22-8-8 22-8-22-22 8 8-22-22-8 22-8-8-22 22 8Z",
  larch: "M60 24v72M60 36l-12 9M60 36l12 9M60 50l-18 13M60 50l18 13M60 66l-24 16M60 66l24 16",
  snowflake: "M60 26v68M31 43l58 34M31 77l58-34M52 32l8 8 8-8M52 88l8-8 8 8",
  seasons: "M60 28a32 32 0 1 1 0 64 32 32 0 1 1 0-64ZM60 28v64M28 60h64",
  calendar: "M32 36h56v52H32ZM32 50h56M46 28v14M74 28v14M44 64h8M58 64h8M72 64h8M44 76h8",
  quill: "M86 26C60 34 46 58 42 90M86 26c-4 26-20 40-38 44M42 90h22",
  camera: "M30 44h14l6-10h20l6 10h14v42H30ZM60 52a12 12 0 1 1 0 24 12 12 0 1 1 0-24Z",
  map: "M26 36l22-8 24 8 22-8v56l-22 8-24-8-22 8ZM48 28v56M72 36v56",
  bell: "M42 76V56a18 18 0 0 1 36 0v20l6 8H36ZM54 90h12M60 30v8",
  clover:
    "M48 37a11 11 0 1 1 0 22 11 11 0 1 1 0-22ZM72 37a11 11 0 1 1 0 22 11 11 0 1 1 0-22ZM48 61a11 11 0 1 1 0 22 11 11 0 1 1 0-22ZM72 61a11 11 0 1 1 0 22 11 11 0 1 1 0-22ZM66 72l16 22",
  backpack: "M40 46a20 20 0 0 1 40 0v42H40ZM50 46v-8a10 10 0 0 1 20 0v8M48 64h24v14H48Z",
  feather: "M82 28c-26 4-38 26-38 54l34-30M44 82l-8 10",
  stairs: "M28 88h16V72h16V56h16V40h16V28",
  lighthouse: "M52 90l4-48h8l4 48ZM50 42h20M56 42v-8h8v8M44 32l-10-4M76 32l10-4M40 90h40",
  ridge: "M20 76l14-10 12 4 14-18 12 8 14-16 14 12M20 88h80",
  secret: "M48 46a12 12 0 1 1 18 10c-4 3-6 6-6 10v4M60 82v2",
};

/** A milestone's icon; an unknown key (a newer backend) gets the trail mark. */
export const milestoneIcon = (icon: string) => MILESTONE_ICONS[icon] ?? MILESTONE_ICONS["first-hike"];
