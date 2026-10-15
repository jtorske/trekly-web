import type { ReactNode } from "react";
import styles from "./FlatLay.module.css";

// Flat-lay silhouettes for the Main setup mat: each core item drawn from
// above as if laid out on the ground. `outline` paths carry the dashed (or,
// once filled, solid) edge; `detail` paths are the fine sketch lines inside.
// Proportions follow the real item so the mat reads like a knolling photo.

interface Shape {
  viewBox: string;
  outline: ReactNode;
  detail: ReactNode;
}

const SHAPES: Record<string, Shape> = {
  // Pack lying flat: lid, haul loop, front pocket, side straps, hip-belt wings.
  backpack: {
    viewBox: "0 0 120 180",
    outline: (
      <>
        <path d="M34 22C34 8 86 8 86 22L90 30C96 34 98 42 98 52L98 132C98 140 96 144 92 146L110 150C114 151 114 160 110 162L92 166C90 172 84 174 78 174L42 174C36 174 30 172 28 166L10 162C6 160 6 151 10 150L28 146C24 144 22 140 22 132L22 52C22 42 24 34 30 30Z" />
        <path d="M54 10C54 2 66 2 66 10" />
      </>
    ),
    detail: (
      <>
        <path d="M30 30C46 37 74 37 90 30" />
        <path d="M44 34V56M76 34V56" />
        <rect x="41" y="54" width="6" height="6" rx="1" />
        <rect x="73" y="54" width="6" height="6" rx="1" />
        <path d="M34 92C34 86 86 86 86 92L84 150C84 156 36 156 36 150Z" />
        <path d="M40 98C52 102 68 102 80 98" />
        <path d="M22 76L34 79M98 76L86 79M22 116L35 116M98 116L85 116" />
        <path d="M28 152C50 159 70 159 92 152" />
        <path d="M14 155L26 154M106 155L94 154" />
      </>
    ),
  },
  // Long tent stuff sack: cinched drawcord end, cord lock, pole bag poking out.
  tent: {
    viewBox: "0 0 240 92",
    outline: (
      <>
        <path d="M40 18C80 12 170 12 196 16C206 18 208 26 208 46C208 66 206 74 196 76C170 80 80 80 40 74C32 68 26 60 22 46C26 32 32 24 40 18Z" />
        <path d="M208 34L228 32C233 32 233 42 228 42L208 40" />
        <path d="M22 46C14 54 10 64 8 76" />
        <rect x="3" y="76" width="9" height="11" rx="2" />
      </>
    ),
    detail: (
      <>
        <path d="M40 18C34 34 34 58 40 74" />
        <path d="M30 32L40 36M28 46L40 46M30 60L40 56" />
        <path d="M62 22C66 34 66 58 62 70" />
        <path d="M196 16C190 32 190 60 196 76" />
        <path d="M48 47C100 44 150 44 190 46" />
        <path d="M120 22C126 28 128 36 126 40M150 70C146 64 146 58 150 54" />
        <path d="M228 37H220" />
      </>
    ),
  },
  // Compression sack standing up: domed cinch, toggle, straps and buckles.
  "sleeping-bag": {
    viewBox: "0 0 120 150",
    outline: (
      <>
        <path d="M38 24C30 22 22 30 20 44L18 120C18 136 30 142 60 142C90 142 102 136 102 120L100 44C98 30 90 22 82 24C74 18 46 18 38 24Z" />
        <path d="M50 22C52 12 68 12 70 22" />
        <path d="M60 13C58 6 64 2 70 4" />
        <rect x="68" y="1" width="6" height="9" rx="2" />
      </>
    ),
    detail: (
      <>
        <path d="M40 26L36 140M80 26L84 140" />
        <rect x="34" y="78" width="8" height="8" rx="1" />
        <rect x="78" y="78" width="8" height="8" rx="1" />
        <path d="M20 58C46 65 74 65 100 58" />
        <path d="M22 126C46 134 74 134 98 126" />
        <path d="M50 40C54 46 54 52 50 56M70 96C66 102 66 108 70 112" />
      </>
    ),
  },
  // Rolled pad on its side: spiral end, valve nub, strap and buckle.
  "sleeping-pad": {
    viewBox: "0 0 240 80",
    outline: (
      <>
        <path d="M30 12H200C214 12 222 26 222 40C222 54 214 68 200 68H30C16 68 10 54 10 40C10 26 16 12 30 12Z" />
        <path d="M10 36H4V44H10" />
      </>
    ),
    detail: (
      <>
        <path d="M200 12C186 12 180 26 180 40C180 54 186 68 200 68" />
        <path d="M200 22C192 22 188 32 188 40C188 50 194 58 202 58C208 58 212 50 212 42C212 34 206 28 200 30C196 32 196 44 202 44" />
        <path d="M90 10V70M98 10V70" />
        <rect x="87" y="34" width="14" height="12" rx="2" />
        <path d="M30 26H84M104 26H178M30 54H84M104 54H178" />
        <path d="M44 36L50 44M50 36L44 44M140 36L146 44M146 36L140 44" />
      </>
    ),
  },
  // Pot from above with handle folded over the lid, canister alongside.
  stove: {
    viewBox: "0 0 124 120",
    outline: (
      <>
        <circle cx="52" cy="66" r="42" />
        <circle cx="106" cy="22" r="14" />
      </>
    ),
    detail: (
      <>
        <circle cx="52" cy="66" r="35" />
        <circle cx="52" cy="66" r="5" />
        <path d="M14 60C30 52 76 58 92 70L90 76C74 66 30 62 14 66Z" />
        <circle cx="38" cy="86" r="1.6" />
        <circle cx="44" cy="90" r="1.6" />
        <circle cx="50" cy="92" r="1.6" />
        <circle cx="106" cy="22" r="9" />
        <circle cx="106" cy="22" r="3" />
      </>
    ),
  },
  // A pair of trail shoes, toes up, laces and heel tabs.
  footwear: {
    viewBox: "0 0 140 132",
    outline: (
      <>
        <path d="M40 8C24 8 14 24 14 46C14 68 20 82 22 96C24 112 30 122 42 122C54 122 60 112 60 96C60 80 64 66 64 46C64 22 56 8 40 8Z" />
        <path d="M100 8C116 8 126 24 126 46C126 68 120 82 118 96C116 112 110 122 98 122C86 122 80 112 80 96C80 80 76 66 76 46C76 22 84 8 100 8Z" />
      </>
    ),
    detail: (
      <>
        <path d="M22 30C30 18 50 18 58 30M82 30C90 18 110 18 118 30" />
        <path d="M30 80C30 70 50 70 50 80L48 104C46 112 34 112 32 104Z" />
        <path d="M90 80C90 70 110 70 110 80L108 104C106 112 94 112 92 104Z" />
        <path d="M30 42L50 50M50 42L30 50M30 54L50 62M50 54L30 62" />
        <path d="M90 42L110 50M110 42L90 50M90 54L110 62M110 54L90 62" />
        <path d="M37 122V128H45V122M95 122V128H103V122" />
      </>
    ),
  },
  // Folded shell: hood on top, centre zip, sleeves folded across.
  "rain-jacket": {
    viewBox: "0 0 150 112",
    outline: (
      <path d="M22 26L58 22C60 10 90 10 92 22L128 26C134 27 136 32 136 38L134 98C134 103 130 106 124 106H26C20 106 16 103 16 98L14 38C14 32 16 27 22 26Z" />
    ),
    detail: (
      <>
        <path d="M62 22C66 30 84 30 88 22" />
        <path d="M75 30V106" />
        <rect x="72" y="34" width="6" height="8" rx="1" />
        <path d="M16 44C40 50 60 60 70 76M134 44C110 50 90 60 80 76" />
        <path d="M18 96H132" />
        <path d="M92 48L112 46" />
      </>
    ),
  },
};

export function hasSilhouette(slotKey: string): boolean {
  return slotKey in SHAPES;
}

export function Silhouette({ slotKey, className }: { slotKey: string; className?: string }) {
  const shape = SHAPES[slotKey];
  if (!shape) return null;
  return (
    <svg className={`${styles.svg} ${className ?? ""}`} viewBox={shape.viewBox} aria-hidden="true" focusable="false">
      <g className={styles.outline}>{shape.outline}</g>
      <g className={styles.detail}>{shape.detail}</g>
    </svg>
  );
}

/** Circled "+" drawn in the same line weight as the silhouettes. */
export function PlusMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 7v10M7 12h10" />
    </svg>
  );
}
