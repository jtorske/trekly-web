/**
 * The Gear mat: each zone is a top-level catalogue category, and each slot in
 * a zone is a specific gear type backed by one or more catalogue
 * subcategories. A slot's product picker queries the API with exactly those
 * subcategories, so the backpack picker can never return tents or stoves.
 *
 * Slot/inventory rule: every owned item belongs to exactly one slot, found
 * from its category. A slot is "filled" when the user owns at least one item
 * in it; additional items appear as their own tiles with an "Add another"
 * action, so an occupied slot never keeps its empty prompt.
 */

import type { GearItem } from "@/lib/gearApi";
import type { IconKey } from "./icons";

export interface Slot {
  key: string;
  /** Singular label, e.g. "Backpack". */
  label: string;
  /** Used in "Choose your …" and "Add another …". */
  noun: string;
  zone: string;
  icon: IconKey;
  /** Catalogue subcategory slugs this slot covers; the first is the default for custom items. */
  categories: string[];
  /** Core slots form the showcase setup; the rest live under "More gear". */
  core?: boolean;
  /** Only one item makes sense in this slot, so no "add another" is offered. */
  single?: boolean;
}

export interface Zone {
  slug: string;
  label: string;
  slots: Slot[];
}

const zone = (slug: string, label: string, slots: Omit<Slot, "zone">[]): Zone => ({
  slug,
  label,
  slots: slots.map((slot) => ({ ...slot, zone: slug })),
});

export const ZONES: Zone[] = [
  zone("backpack", "Backpack", [
    { core: true, key: "backpack", label: "Backpack", noun: "backpack", icon: "backpack", categories: ["backpacks"] },
    { key: "pack-accessories", label: "Pack cover or liner", noun: "pack cover or liner", icon: "packCover", categories: ["pack-accessories"] },
  ]),
  zone("shelter", "Shelter", [
    { core: true, key: "tent", label: "Tent or shelter", noun: "tent or shelter", icon: "tent", categories: ["tents", "tarps", "bivy-sacks"] },
    { key: "shelter-extras", label: "Footprint & stakes", noun: "footprint or stakes", icon: "stake", categories: ["footprints", "stakes-guylines"] },
  ]),
  zone("sleep", "Sleep system", [
    { core: true, key: "sleeping-bag", label: "Sleeping bag or quilt", noun: "sleeping bag or quilt", icon: "sleepingBag", categories: ["sleeping-bags", "quilts", "sleep-liners"] },
    { core: true, key: "sleeping-pad", label: "Sleeping pad", noun: "sleeping pad", icon: "sleepingPad", categories: ["sleeping-pads"] },
    { key: "pillow", label: "Pillow", noun: "pillow", icon: "pillow", categories: ["pillows"] },
  ]),
  zone("clothing", "Clothing", [
    { core: true, key: "rain-jacket", label: "Rain jacket", noun: "rain jacket", icon: "rainJacket", categories: ["rainwear", "wind-layers"] },
    { key: "insulation", label: "Insulating layer", noun: "insulating layer", icon: "insulation", categories: ["insulation", "fleece-midlayers"] },
    { key: "base-layer", label: "Base layer", noun: "base layer", icon: "baseLayer", categories: ["base-layers", "headwear-gloves"] },
  ]),
  zone("cooking", "Cooking", [
    { core: true, key: "stove", label: "Stove or cook system", noun: "stove or cook system", icon: "stove", categories: ["stoves"] },
    { key: "cookware", label: "Cookware", noun: "pot, mug or utensil", icon: "pot", categories: ["cookware", "utensils", "fuel-accessories"] },
    { key: "food-storage", label: "Food storage", noun: "bear canister or food bag", icon: "canister", categories: ["food-storage"] },
  ]),
  zone("hydration", "Hydration", [
    { key: "water-filter", label: "Water filter", noun: "water filter or purifier", icon: "filter", categories: ["water-treatment"] },
    { key: "water-bottle", label: "Water bottle", noun: "bottle or reservoir", icon: "bottle", categories: ["bottles-reservoirs"] },
  ]),
  zone("footwear", "Footwear", [
    { core: true, key: "footwear", label: "Boots or trail shoes", noun: "boots or trail shoes", icon: "boot", categories: ["hiking-boots", "trail-runners"] },
    { key: "camp-shoes", label: "Gaiters & camp shoes", noun: "gaiters or camp shoes", icon: "sandal", categories: ["gaiters", "camp-shoes"] },
  ]),
  zone("navigation", "Navigation", [
    { key: "gps", label: "GPS or messenger", noun: "GPS or satellite messenger", icon: "gps", categories: ["gps-satellite", "watches"] },
    { key: "compass", label: "Compass", noun: "compass", icon: "compass", categories: ["compasses"] },
  ]),
  zone("safety", "Safety", [
    { key: "first-aid", label: "First aid kit", noun: "first aid kit", icon: "firstAid", categories: ["first-aid", "emergency"] },
    { key: "bear-safety", label: "Bear spray", noun: "bear safety gear", icon: "spray", categories: ["bear-safety"] },
  ]),
  zone("accessories", "Accessories", [
    { key: "headlamp", label: "Headlamp", noun: "headlamp", icon: "headlamp", categories: ["lighting"] },
    { key: "trekking-poles", label: "Trekking poles", noun: "trekking poles", icon: "poles", categories: ["trekking-poles"] },
    { key: "storage", label: "Dry bags & stuff sacks", noun: "dry bag or stuff sack", icon: "dryBag", categories: ["storage"] },
    { key: "power", label: "Power bank", noun: "power bank", icon: "battery", categories: ["power"] },
    { key: "other", label: "Other gear", noun: "piece of gear", icon: "generic", categories: ["repair", "misc"] },
  ]),
];

export const ALL_SLOTS: Slot[] = ZONES.flatMap((z) => z.slots);

/** Showcase order for the main setup. */
const CORE_ORDER = ["backpack", "tent", "sleeping-bag", "sleeping-pad", "stove", "footwear", "rain-jacket"];
export const CORE_SLOTS: Slot[] = CORE_ORDER.map((key) => ALL_SLOTS.find((slot) => slot.key === key)!);

/** Zones with their non-core slots only, for the "More gear" section. */
export const MORE_ZONES: Zone[] = ZONES.map((z) => ({ ...z, slots: z.slots.filter((slot) => !slot.core) })).filter(
  (z) => z.slots.length > 0,
);

const SLOT_BY_CATEGORY = new Map<string, Slot>();
for (const slot of ALL_SLOTS) {
  for (const category of slot.categories) SLOT_BY_CATEGORY.set(category, slot);
}

/** Every catalogue subcategory must map to exactly one slot. */
export function slotForCategory(categorySlug: string, topSlug?: string): Slot {
  const direct = SLOT_BY_CATEGORY.get(categorySlug);
  if (direct) return direct;
  // An item filed under a top-level category (custom items can be) goes to
  // that zone's first slot rather than disappearing from the mat.
  const zoneMatch = ZONES.find((z) => z.slug === (topSlug ?? categorySlug));
  return zoneMatch ? zoneMatch.slots[zoneMatch.slots.length - 1] : ALL_SLOTS[ALL_SLOTS.length - 1];
}

export function slotForItem(item: GearItem): Slot {
  return slotForCategory(item.category.slug, item.category.top_slug);
}

export function slotByKey(key: string): Slot | undefined {
  return ALL_SLOTS.find((slot) => slot.key === key);
}

export function groupItemsBySlot(items: GearItem[]): Map<string, GearItem[]> {
  const grouped = new Map<string, GearItem[]>();
  for (const item of items) {
    const key = slotForItem(item).key;
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }
  return grouped;
}

export function zoneCoverage(items: GearItem[]): { filled: number; total: number } {
  const zones = new Set(items.map((item) => slotForItem(item).zone));
  return { filled: zones.size, total: ZONES.length };
}

export interface GearWarning {
  key: string;
  /** warning: hard to camp without it. note: worth a second look. */
  level: "warning" | "note";
  message: string;
}

const TRIP_CHECKS: { slot: string; level: GearWarning["level"]; message: string }[] = [
  { slot: "tent", level: "warning", message: "No shelter (tent, tarp or bivy)" },
  { slot: "sleeping-bag", level: "warning", message: "No sleeping bag or quilt" },
  { slot: "sleeping-pad", level: "note", message: "No sleeping pad" },
];

/** "Missing core gear" for a trip plan's setup: shelter and sleep system. */
export function missingTripGear(items: GearItem[]): GearWarning[] {
  const present = new Set(items.map((item) => slotForItem(item).key));
  return TRIP_CHECKS.filter((check) => !present.has(check.slot)).map(({ slot, level, message }) => ({
    key: slot,
    level,
    message,
  }));
}
