/**
 * Every number behind the gear page's weight summary, in one place to tune.
 *
 * Base weight is what's on your back before food, water and fuel: packed
 * items only, leaving out worn and consumable ones (baseWeight.ts). The
 * class is the first band whose upper limit the base weight is under.
 */

export interface PackClass {
  key: "super-ultralight" | "ultralight" | "lightweight" | "traditional";
  label: string;
  /** Exclusive upper limit in grams; null for the last band. */
  underGrams: number | null;
}

/** Lightest first; the last band catches everything above. */
export const PACK_CLASSES: PackClass[] = [
  { key: "super-ultralight", label: "Super Ultralight", underGrams: 4500 },
  { key: "ultralight", label: "Ultralight", underGrams: 9000 },
  { key: "lightweight", label: "Lightweight", underGrams: 13500 },
  { key: "traditional", label: "Traditional", underGrams: null },
];

/** Zones (top-level categories) that make up the "Big Three". */
export const BIG_THREE_ZONES = ["backpack", "shelter", "sleep"] as const;

/** Slots whose items count as worn unless the owner says otherwise. */
export const WORN_BY_DEFAULT_SLOTS = ["footwear"];
