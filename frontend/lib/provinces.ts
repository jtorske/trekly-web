/**
 * Canada's 13 provinces and territories, for a profile's home province: the
 * name, the badge colour and the badge motif. The API stores the two-letter
 * code (backend app/provinces.py; a backend test checks the two lists match)
 * and null means "Prefer not to say". "Outside Canada" (OUTSIDE_CANADA) is a
 * fourteenth choice with a badge of its own in the same style; province()
 * returns it too, so everything that shows a home badge shows it.
 *
 * Motifs are drawn in the badge's 120 square, inside the centre disc (radius
 * 29 around 60,60), as layers:
 *   fill   — the cream motif itself
 *   stroke — cream lines (waves, masts, aurora)
 *   accent — details in the badge colour, drawn over the motif
 *   faint  — cream at low opacity, for depth (a distant ridge, light beams)
 */

export type ProvinceCode = "AB" | "BC" | "MB" | "NB" | "NL" | "NS" | "NT" | "NU" | "ON" | "PE" | "QC" | "SK" | "YT";

export const OUTSIDE_CANADA = "outside";
/** What a profile's home can be: a province or territory, or outside Canada. */
export type HomeCode = ProvinceCode | typeof OUTSIDE_CANADA;

export type MotifLayer = "fill" | "stroke" | "accent" | "faint";

export interface Province {
  code: HomeCode;
  name: string;
  kind: "province" | "territory" | "outside";
  /** The badge's edge text when it isn't the name (Outside Canada's label). */
  badgeName?: string;
  /** The badge's foot text when it isn't the code. */
  badgeFoot?: string;
  colour: string;
  /** What the motif shows, for the badge's accessible name. */
  motif: string;
  shapes: { layer: MotifLayer; d: string; width?: number }[];
}

const circle = (cx: number, cy: number, r: number) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${r * 2} 0a${r} ${r} 0 1 0 ${-r * 2} 0Z`;

/** A gentle wave line across the disc at height y. */
const waves = (y: number, amp = 3) =>
  `M30 ${y}${Array.from({ length: 5 }, (_, i) => `c4 ${i % 2 ? amp : -amp} 8 ${i % 2 ? amp : -amp} 12 0`).join("")}`;

/** A wheat ear: a stem with paired grains and one on top. */
function wheat(): string {
  const grains = [74, 66, 58, 50].flatMap((y) => [
    `M59 ${y}C52 ${y - 1} 49 ${y - 6} 50 ${y - 11}C56 ${y - 10} 59 ${y - 6} 59 ${y}Z`,
    `M61 ${y}C68 ${y - 1} 71 ${y - 6} 70 ${y - 11}C64 ${y - 10} 61 ${y - 6} 61 ${y}Z`,
  ]);
  return [...grains, "M60 45C56 41 56 36 60 31C64 36 64 41 60 45Z"].join("");
}

/** A small spruce standing on y=80. */
const spruce = (x: number, h: number) => {
  const notch = 80 - h * 0.5;
  return `M${x} ${80 - h}L${x + 3.2} ${notch}H${x + 1.6}L${x + 5} 80H${x - 5}L${x - 1.6} ${notch}H${x - 3.2}Z`;
};

const sparkle = (x: number, y: number, s: number) =>
  `M${x} ${y - s}L${x + s * 0.3} ${y - s * 0.3}L${x + s} ${y}L${x + s * 0.3} ${y + s * 0.3}L${x} ${y + s}L${x - s * 0.3} ${y + s * 0.3}L${x - s} ${y}L${x - s * 0.3} ${y - s * 0.3}Z`;

/** Trillium petals and sepals: one drawn pointing up, copied round the centre. */
function trillium(): { petals: string; sepals: string } {
  const rotate = (d: string, deg: number) => {
    const a = (deg * Math.PI) / 180;
    const cos = Math.cos(a);
    const sin = Math.sin(a);
    return d.replace(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g, (_, xs: string, ys: string) => {
      const x = Number(xs) - 60;
      const y = Number(ys) - 60;
      return `${Math.round((60 + x * cos - y * sin) * 100) / 100} ${Math.round((60 + x * sin + y * cos) * 100) / 100}`;
    });
  };
  const petal = "M60 60C51 52 51 41 60 34C69 41 69 52 60 60Z";
  const sepal = "M60 60C57 53 58 45 60 38C62 45 63 53 60 60Z";
  return {
    petals: [0, 120, 240].map((deg) => rotate(petal, deg)).join(""),
    sepals: [60, 180, 300].map((deg) => rotate(sepal, deg)).join(""),
  };
}

const TRILLIUM = trillium();

export const PROVINCES: Province[] = [
  {
    code: "AB",
    name: "Alberta",
    kind: "province",
    colour: "#3d5f86",
    motif: "Rocky Mountain peaks",
    shapes: [
      { layer: "fill", d: "M28 84L44 58L51 66L62 44L74 62L79 56L92 84Z" },
      { layer: "accent", d: "M62 44L57 53L61 51L64 54L67 51.5ZM44 58L40.5 63.5L44 62L47.5 62.5Z" },
    ],
  },
  {
    code: "BC",
    name: "British Columbia",
    kind: "province",
    colour: "#2f6b5d",
    motif: "an evergreen on the coast",
    shapes: [
      { layer: "faint", d: "M56 75L72 52L92 75Z" },
      { layer: "fill", d: "M48 34L57 48H52L60 60H54L62 73H34L42 60H36L44 48H39ZM46 73h4v5h-4Z" },
      { layer: "stroke", d: waves(81), width: 2.2 },
    ],
  },
  {
    code: "MB",
    name: "Manitoba",
    kind: "province",
    colour: "#8a4b2d",
    motif: "a bison",
    shapes: [
      {
        layer: "fill",
        d:
          "M34 68L33 61C33 56 36 52 40 51C42 46 48 42 56 42C64 42 70 46 76 50C82 51 86 54 87 60L88 66H86L85 78H81L80 69H76" +
          "L75 78H71L70 68C62 70 56 70 52 69L51 78H47L46 70L44 78H40V72C38 72 36 71 34 68Z",
      },
      { layer: "stroke", d: "M41 51C38.5 47.5 40.5 45 44 46", width: 2 },
      { layer: "accent", d: circle(38.5, 57, 1.1) },
    ],
  },
  {
    code: "NB",
    name: "New Brunswick",
    kind: "province",
    colour: "#9a3434",
    motif: "a sailing ship",
    shapes: [
      { layer: "stroke", d: "M60 67V35", width: 2 },
      { layer: "fill", d: "M46 42C52 44 68 44 74 42C72 50 72 56 74 62C68 60 52 60 46 62C48 56 48 50 46 42ZM60 35L69 37.5L60 40Z" },
      { layer: "fill", d: "M34 66H86L78 76H42Z" },
      { layer: "stroke", d: waves(82), width: 2 },
    ],
  },
  {
    code: "NL",
    name: "Newfoundland and Labrador",
    kind: "province",
    colour: "#5c4a7e",
    motif: "an iceberg",
    shapes: [
      { layer: "faint", d: "M40 69H80L72 83L56 87L46 81Z" },
      { layer: "fill", d: "M37 65L46 50L52 54L60 37L68 50L74 47L83 65Z" },
      { layer: "accent", d: "M60 37L68 50L74 47L83 65H67Z" },
      { layer: "stroke", d: waves(66, 2), width: 2 },
    ],
  },
  {
    code: "NS",
    name: "Nova Scotia",
    kind: "province",
    colour: "#2a5f7c",
    motif: "a lighthouse on the rocks",
    shapes: [
      { layer: "faint", d: "M56 43L32 36V50ZM64 43L88 36V50Z" },
      { layer: "fill", d: "M55 78L57.5 48H62.5L65 78ZM54 45.5h12v2.5H54ZM56.5 39.5h7v6h-7ZM55 39.5L60 34.5L65 39.5Z" },
      { layer: "accent", d: "M56.5 59H63.5L64 66H56Z" },
      { layer: "fill", d: "M30 88C36 79 45 76 52 78C56 74 64 74 68 78C75 76 84 79 90 88Z" },
    ],
  },
  {
    code: "NT",
    name: "Northwest Territories",
    kind: "territory",
    colour: "#1f4060",
    motif: "the northern lights over spruce",
    shapes: [
      { layer: "stroke", d: "M30 45c8-6 14 4 22-2s14-8 22-2 12 4 18 0", width: 3 },
      { layer: "faint", d: "M30 52c8-5 14 3 22-1s14-6 22-1 12 3 18 0v4c-6 3-12-2-18 1s-14-4-22 1-14-3-22 1Z" },
      { layer: "fill", d: [spruce(37, 15), spruce(47, 22), spruce(57, 15), spruce(66, 24), spruce(76, 18), spruce(85, 13), "M28 80H92V92H28Z"].join("") },
    ],
  },
  {
    code: "NU",
    name: "Nunavut",
    kind: "territory",
    colour: "#5d646e",
    motif: "an inukshuk",
    shapes: [
      {
        layer: "fill",
        d: "M54 37h12v9.5H54ZM35 47.5h50v6H35ZM53 54.5h14V61H53ZM45 62h30v5.5H45ZM48 68.5h7V82h-7ZM65 68.5h7V82h-7ZM28 83H92V92H28Z",
      },
    ],
  },
  {
    code: "ON",
    name: "Ontario",
    kind: "province",
    colour: "#3f6a35",
    motif: "a trillium",
    shapes: [
      { layer: "faint", d: TRILLIUM.sepals },
      { layer: "fill", d: TRILLIUM.petals },
      { layer: "accent", d: circle(60, 60, 3.5) },
    ],
  },
  {
    code: "PE",
    name: "Prince Edward Island",
    kind: "province",
    colour: "#a9503a",
    motif: "an oak tree",
    shapes: [
      { layer: "fill", d: [circle(60, 47, 13), circle(48.5, 54, 10), circle(71.5, 54, 10), circle(55, 60, 9), circle(65, 60, 9)].join("") },
      { layer: "fill", d: "M57 62L56 77H64L63 62Z" },
      { layer: "stroke", d: "M34 78H86", width: 2 },
    ],
  },
  {
    code: "QC",
    name: "Quebec",
    kind: "province",
    colour: "#23498e",
    motif: "a fleur-de-lis",
    shapes: [
      {
        layer: "fill",
        d:
          "M60 32C67 40 68 50 60 62C52 50 53 40 60 32Z" +
          "M62 62C68 62 78 60 80 52C82 45 77 41 72 43C76 46 75 52 70 54C67 55 64 56 62 58Z" +
          "M58 62C52 62 42 60 40 52C38 45 43 41 48 43C44 46 45 52 50 54C53 55 56 56 58 58Z" +
          "M45 62.5h30v5H45Z" +
          "M55 68.5C55 74 52 78 47 80C52 81 57 79 60 74C63 79 68 81 73 80C68 78 65 74 65 68.5Z",
      },
    ],
  },
  {
    code: "SK",
    name: "Saskatchewan",
    kind: "province",
    colour: "#9a7016",
    motif: "an ear of wheat",
    shapes: [
      { layer: "stroke", d: "M60 86V44", width: 2 },
      { layer: "fill", d: wheat() },
    ],
  },
  {
    code: "YT",
    name: "Yukon",
    kind: "territory",
    colour: "#9a3a6a",
    motif: "a gold pan with nuggets",
    shapes: [
      { layer: "faint", d: "M30 60L42 46L50 54L60 42L72 54L78 48L90 60Z" },
      { layer: "fill", d: "M34 64a26 12 0 1 0 52 0a26 12 0 1 0 -52 0Z" },
      { layer: "accent", d: "M42 63a18 7 0 1 0 36 0a18 7 0 1 0 -36 0Z" },
      { layer: "fill", d: [circle(53, 63, 2.2), circle(61, 61, 1.8), circle(67, 64, 2.4), sparkle(48, 40, 4), sparkle(72, 36, 3)].join("") },
    ],
  },
];

/**
 * Two designs for the "Outside Canada" badge, in the province badge style.
 * OUTSIDE_CANADA_DESIGN picks the one in use.
 */
export const OUTSIDE_CANADA_DESIGNS: Record<"globe" | "compass", Province> = {
  // A: a globe, "From away" (what Maritimers call anyone who isn't from here).
  globe: {
    code: OUTSIDE_CANADA,
    name: "Outside Canada",
    kind: "outside",
    badgeName: "From away",
    badgeFoot: "✦",
    colour: "#3f6470",
    motif: "a globe",
    shapes: [
      { layer: "faint", d: circle(60, 60, 19) },
      { layer: "stroke", d: `${circle(60, 60, 19)}M60 41a8.5 19 0 1 0 0 38a8.5 19 0 1 0 0-38ZM60 41V79`, width: 2.2 },
      { layer: "stroke", d: "M41 60H79M44.5 50H75.5M44.5 70H75.5", width: 1.8 },
    ],
  },
  // B: a compass rose, "Visitor".
  compass: {
    code: OUTSIDE_CANADA,
    name: "Outside Canada",
    kind: "outside",
    badgeName: "Visitor",
    badgeFoot: "✦",
    colour: "#7a5a2c",
    motif: "a compass rose",
    shapes: [
      { layer: "stroke", d: circle(60, 60, 22), width: 1.6 },
      { layer: "faint", d: "M60 60L71 49L64 60L71 71ZM60 60L49 49L56 60L49 71Z" },
      { layer: "fill", d: "M60 34L64.5 55.5L86 60L64.5 64.5L60 86L55.5 64.5L34 60L55.5 55.5Z" },
      { layer: "accent", d: `M60 34L64.5 55.5L60 60L55.5 55.5Z${circle(60, 60, 2.4)}` },
    ],
  },
};

export const OUTSIDE_CANADA_DESIGN: keyof typeof OUTSIDE_CANADA_DESIGNS = "globe";
export const OUTSIDE: Province = OUTSIDE_CANADA_DESIGNS[OUTSIDE_CANADA_DESIGN];

const BY_CODE = new Map<string, Province>([...PROVINCES.map((p) => [p.code, p] as const), [OUTSIDE_CANADA, OUTSIDE]]);

/** The province, territory or Outside Canada for a stored home code. */
export function province(code: string | null | undefined): Province | null {
  return (code && BY_CODE.get(code)) || null;
}

/** "Home province", "Home territory", or "Home" for Outside Canada. */
export function homeLabel(p: Province): string {
  if (p.kind === "outside") return "Home";
  return p.kind === "territory" ? "Home territory" : "Home province";
}

/** Provinces then territories, each A–Z, then Outside Canada, for the Edit profile menu. */
export function provinceOptions(): { label: string; options: Province[] }[] {
  const sorted = [...PROVINCES].sort((a, b) => a.name.localeCompare(b.name));
  return [
    { label: "Provinces", options: sorted.filter((p) => p.kind === "province") },
    { label: "Territories", options: sorted.filter((p) => p.kind === "territory") },
    { label: "Elsewhere", options: [OUTSIDE] },
  ];
}
