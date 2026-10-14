import type { ReactNode } from "react";

// Original Trekly line illustrations on a shared 48×48 grid, so every item on
// the mat reads as one coherent set whether or not a product photo exists.
const PATHS = {
  backpack: (
    <>
      <path d="M16 14c0-5 3.5-8 8-8s8 3 8 8" />
      <rect x="11" y="14" width="26" height="28" rx="7" />
      <path d="M17 28h14v9H17z" />
      <path d="M20 14v5m8-5v5" />
    </>
  ),
  packCover: (
    <>
      <path d="M12 16c0-6 5-10 12-10s12 4 12 10v20c0 4-3 6-6 6H18c-3 0-6-2-6-6Z" />
      <path d="M12 22c4 2 20 2 24 0" />
    </>
  ),
  tent: (
    <>
      <path d="M4 40 24 9l20 31Z" />
      <path d="M24 9v31" />
      <path d="M17 40l7-12 7 12" />
    </>
  ),
  stake: (
    <>
      <path d="M18 6h6l2 4-4 32-4-32Z" />
      <path d="M30 10c4 4 4 10 0 14" />
    </>
  ),
  sleepingBag: (
    <>
      <path d="M17 4h14a6 6 0 0 1 6 6v28a6 6 0 0 1-6 6H17a6 6 0 0 1-6-6V10a6 6 0 0 1 6-6Z" />
      <path d="M15 14c3 2 15 2 18 0" />
      <path d="M11 24h26M11 33h26" />
    </>
  ),
  sleepingPad: (
    <>
      <rect x="14" y="4" width="20" height="40" rx="4" />
      <path d="M14 12h20M14 20h20M14 28h20M14 36h20" />
    </>
  ),
  pillow: (
    <>
      <path d="M8 18c0-4 4-6 16-6s16 2 16 6v12c0 4-4 6-16 6S8 34 8 30Z" />
      <path d="M14 24h20" />
    </>
  ),
  rainJacket: (
    <>
      <path d="M18 6h12l10 8-4 7-3-2v23H15V19l-3 2-4-7Z" />
      <path d="M18 6c0 4 3 6 6 6s6-2 6-6" />
      <path d="M24 12v30" />
    </>
  ),
  insulation: (
    <>
      <path d="M18 6h12l10 8-4 7-3-2v23H15V19l-3 2-4-7Z" />
      <path d="M15 24h18M15 31h18M15 38h18" />
    </>
  ),
  baseLayer: (
    <>
      <path d="M18 7h12l9 7-3 5-3-2v25H15V17l-3 2-3-5Z" />
      <path d="M20 7c1 3 7 3 8 0" />
    </>
  ),
  stove: (
    <>
      <path d="M14 42h20l-3-14H17Z" />
      <path d="M12 28h24" />
      <path d="M18 22c0-3 3-4 3-8m6 8c0-3 3-4 3-8" />
      <path d="M24 22v-6" />
    </>
  ),
  pot: (
    <>
      <path d="M10 18h28v16a8 8 0 0 1-8 8H18a8 8 0 0 1-8-8Z" />
      <path d="M8 18h32" />
      <path d="M20 12h8" />
      <path d="M38 22h6" />
    </>
  ),
  canister: (
    <>
      <rect x="13" y="8" width="22" height="34" rx="6" />
      <path d="M13 16h22M13 34h22" />
      <path d="M21 8V5h6v3" />
    </>
  ),
  filter: (
    <>
      <rect x="17" y="12" width="14" height="30" rx="5" />
      <path d="M21 12V6h6v6" />
      <path d="M17 22h14M17 30h14" />
    </>
  ),
  bottle: (
    <>
      <path d="M19 4h10v6l4 5v25a4 4 0 0 1-4 4H19a4 4 0 0 1-4-4V15l4-5Z" />
      <path d="M15 24h18" />
    </>
  ),
  boot: (
    <>
      <path d="M14 6h12v20l12 6c3 1 4 4 4 6v4H8V30c0-4 2-6 6-8Z" />
      <path d="M8 38h34" />
      <path d="M14 14h12M14 20h12" />
    </>
  ),
  sandal: (
    <>
      <path d="M12 30c0-10 4-22 12-22s12 12 12 22c0 6-4 10-12 10S12 36 12 30Z" />
      <path d="M14 22h20M13 30h22" />
    </>
  ),
  gps: (
    <>
      <rect x="14" y="10" width="20" height="32" rx="5" />
      <path d="M20 10V4" />
      <rect x="18" y="16" width="12" height="10" rx="2" />
      <circle cx="24" cy="34" r="2.5" />
    </>
  ),
  compass: (
    <>
      <circle cx="24" cy="24" r="17" />
      <path d="m30 18-4 9-8 3 4-9Z" />
      <path d="M24 7v4M24 37v4M7 24h4M37 24h4" />
    </>
  ),
  firstAid: (
    <>
      <rect x="6" y="13" width="36" height="27" rx="5" />
      <path d="M18 13V8h12v5" />
      <path d="M24 21v11m-5.5-5.5h11" />
    </>
  ),
  spray: (
    <>
      <rect x="16" y="14" width="16" height="28" rx="5" />
      <path d="M20 14V8h8v6" />
      <path d="M28 10h6M36 6l3-2M36 12l3 2" />
    </>
  ),
  headlamp: (
    <>
      <path d="M6 24c0-9 8-15 18-15s18 6 18 15" />
      <rect x="15" y="22" width="18" height="13" rx="4" />
      <circle cx="24" cy="28.5" r="3.5" />
    </>
  ),
  poles: (
    <>
      <path d="M17 6v36M31 6v36" />
      <path d="M14 6h6M28 6h6" />
      <path d="M15 34h4M29 34h4" />
    </>
  ),
  dryBag: (
    <>
      <path d="M14 14h20l2 26a4 4 0 0 1-4 4H16a4 4 0 0 1-4-4Z" />
      <path d="M13 9h22v5H13z" />
      <path d="M20 9V5h8v4" />
    </>
  ),
  battery: (
    <>
      <rect x="10" y="12" width="28" height="24" rx="4" />
      <path d="M38 20h3v8h-3" />
      <path d="m25 16-5 9h7l-4 7" />
    </>
  ),
  generic: (
    <>
      <rect x="9" y="13" width="30" height="26" rx="5" />
      <path d="M17 13V9h14v4" />
      <path d="M9 23h30" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconKey = keyof typeof PATHS;

export function GearIcon({ icon, className }: { icon: IconKey; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[icon] ?? PATHS.generic}
    </svg>
  );
}
