import type { ReactNode } from "react";
import type { GearCategory, GearIconKey } from "./gearCatalog";

// Simple line illustrations on a shared 48×48 grid so every item in the flat
// lay reads as one consistent set, whether or not we know the exact product.
const PATHS: Record<GearIconKey, ReactNode> = {
  backpack: (
    <>
      <path d="M16 14c0-5 3.5-8 8-8s8 3 8 8" />
      <rect x="11" y="14" width="26" height="28" rx="7" />
      <path d="M17 28h14v9H17z" />
      <path d="M20 14v5m8-5v5" />
    </>
  ),
  tent: (
    <>
      <path d="M4 40 24 9l20 31Z" />
      <path d="M24 9v31" />
      <path d="M17 40l7-12 7 12" />
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
  headlamp: (
    <>
      <path d="M6 24c0-9 8-15 18-15s18 6 18 15" />
      <rect x="15" y="22" width="18" height="13" rx="4" />
      <circle cx="24" cy="28.5" r="3.5" />
    </>
  ),
  firstAid: (
    <>
      <rect x="6" y="13" width="36" height="27" rx="5" />
      <path d="M18 13V8h12v5" />
      <path d="M24 21v11m-5.5-5.5h11" />
    </>
  ),
  generic: (
    <>
      <rect x="9" y="13" width="30" height="26" rx="5" />
      <path d="M17 13V9h14v4" />
      <path d="M9 23h30" />
    </>
  ),
};

const CATEGORY_ICONS: Record<GearCategory, GearIconKey> = {
  pack: "backpack",
  shelter: "tent",
  sleep: "sleepingBag",
  clothing: "insulation",
  cooking: "pot",
  water: "bottle",
  accessories: "generic",
};

export function iconForCategory(category: GearCategory): GearIconKey {
  return CATEGORY_ICONS[category];
}

export function GearIcon({
  icon,
  className,
}: {
  icon: GearIconKey;
  className?: string;
}) {
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
      {PATHS[icon]}
    </svg>
  );
}
