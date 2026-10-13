export type GearCategory =
  | "pack"
  | "shelter"
  | "sleep"
  | "clothing"
  | "cooking"
  | "water"
  | "accessories";

export const GEAR_CATEGORIES: { key: GearCategory; label: string }[] = [
  { key: "pack", label: "Backpack" },
  { key: "shelter", label: "Shelter" },
  { key: "sleep", label: "Sleep system" },
  { key: "clothing", label: "Clothing" },
  { key: "cooking", label: "Cooking" },
  { key: "water", label: "Water" },
  { key: "accessories", label: "Accessories" },
];

export const CATEGORY_LABELS = Object.fromEntries(
  GEAR_CATEGORIES.map((c) => [c.key, c.label]),
) as Record<GearCategory, string>;

/** Icon keys drawn by GearIcon — one per essential slot plus category fallbacks. */
export type GearIconKey =
  | "backpack"
  | "tent"
  | "sleepingBag"
  | "sleepingPad"
  | "rainJacket"
  | "insulation"
  | "stove"
  | "pot"
  | "filter"
  | "bottle"
  | "headlamp"
  | "firstAid"
  | "generic";

export interface EssentialSlot {
  key: string;
  category: GearCategory;
  label: string;
  icon: GearIconKey;
}

/** The core kit a multi-day backpacking trip needs; drives the progress meter. */
export const ESSENTIAL_SLOTS: EssentialSlot[] = [
  { key: "backpack", category: "pack", label: "Backpack", icon: "backpack" },
  { key: "tent", category: "shelter", label: "Tent or shelter", icon: "tent" },
  { key: "sleeping_bag", category: "sleep", label: "Sleeping bag or quilt", icon: "sleepingBag" },
  { key: "sleeping_pad", category: "sleep", label: "Sleeping pad", icon: "sleepingPad" },
  { key: "rain_jacket", category: "clothing", label: "Rain jacket", icon: "rainJacket" },
  { key: "insulation", category: "clothing", label: "Insulating layer", icon: "insulation" },
  { key: "stove", category: "cooking", label: "Stove", icon: "stove" },
  { key: "cook_pot", category: "cooking", label: "Cook pot", icon: "pot" },
  { key: "water_filter", category: "water", label: "Water filter", icon: "filter" },
  { key: "water_storage", category: "water", label: "Bottles or reservoir", icon: "bottle" },
  { key: "headlamp", category: "accessories", label: "Headlamp", icon: "headlamp" },
  { key: "first_aid", category: "accessories", label: "First aid kit", icon: "firstAid" },
];

export const SLOTS_BY_KEY = Object.fromEntries(
  ESSENTIAL_SLOTS.map((slot) => [slot.key, slot]),
) as Record<string, EssentialSlot>;

/**
 * Generic items with typical weights, offered when the catalogue has nothing
 * for a slot. Users can always override the name and weight.
 */
export interface GenericGear {
  name: string;
  category: GearCategory;
  slot?: string;
  weightG: number;
}

export const GENERIC_GEAR: GenericGear[] = [
  { name: "Backpack (50–60 L)", category: "pack", slot: "backpack", weightG: 1600 },
  { name: "Ultralight backpack (40 L)", category: "pack", slot: "backpack", weightG: 850 },
  { name: "Pack rain cover", category: "pack", weightG: 120 },
  { name: "Two-person backpacking tent", category: "shelter", slot: "tent", weightG: 1800 },
  { name: "One-person tent", category: "shelter", slot: "tent", weightG: 1150 },
  { name: "Tarp shelter", category: "shelter", slot: "tent", weightG: 450 },
  { name: "Tent footprint", category: "shelter", weightG: 200 },
  { name: "Down quilt", category: "sleep", slot: "sleeping_bag", weightG: 650 },
  { name: "Inflatable sleeping pad", category: "sleep", slot: "sleeping_pad", weightG: 450 },
  { name: "Foam sleeping pad", category: "sleep", slot: "sleeping_pad", weightG: 400 },
  { name: "Inflatable pillow", category: "sleep", weightG: 60 },
  { name: "Rain jacket", category: "clothing", slot: "rain_jacket", weightG: 300 },
  { name: "Fleece jacket", category: "clothing", slot: "insulation", weightG: 350 },
  { name: "Puffy jacket", category: "clothing", slot: "insulation", weightG: 400 },
  { name: "Rain pants", category: "clothing", weightG: 220 },
  { name: "Canister stove", category: "cooking", slot: "stove", weightG: 85 },
  { name: "Fuel canister (230 g)", category: "cooking", weightG: 360 },
  { name: "Titanium pot (900 mL)", category: "cooking", slot: "cook_pot", weightG: 120 },
  { name: "Long-handled spoon", category: "cooking", weightG: 15 },
  { name: "Squeeze water filter", category: "water", slot: "water_filter", weightG: 85 },
  { name: "Pump water filter", category: "water", slot: "water_filter", weightG: 310 },
  { name: "Water bottle (1 L)", category: "water", slot: "water_storage", weightG: 40 },
  { name: "Hydration reservoir (2 L)", category: "water", slot: "water_storage", weightG: 180 },
  { name: "Trekking poles", category: "accessories", weightG: 480 },
];

/** Maps the existing gear_items catalogue categories onto the gear page's. */
export const CATALOG_CATEGORY_MAP: Record<string, GearCategory> = {
  shelter: "shelter",
  sleep: "sleep",
  kitchen: "cooking",
  clothing: "clothing",
  navigation: "accessories",
  first_aid: "accessories",
  essentials: "accessories",
  safety: "accessories",
  other: "accessories",
};

/** Best-guess essential slot for a catalogue item, matched by name. */
export function guessSlot(name: string, category: GearCategory): string | undefined {
  const lower = name.toLowerCase();
  if (lower.includes("sleeping bag") || lower.includes("quilt")) return "sleeping_bag";
  if (lower.includes("sleeping pad")) return "sleeping_pad";
  if (lower.includes("headlamp")) return "headlamp";
  if (lower.includes("first aid")) return "first_aid";
  if (lower.includes("insulated") || lower.includes("puffy") || lower.includes("fleece")) {
    return "insulation";
  }
  if (lower.includes("rain jacket")) return "rain_jacket";
  if (category === "pack" && lower.includes("pack")) return "backpack";
  return undefined;
}

const GRAMS_PER_OUNCE = 28.3495;

export function gramsToOunces(grams: number): number {
  return Math.round((grams / GRAMS_PER_OUNCE) * 10) / 10;
}

export function ouncesToGrams(ounces: number): number {
  return Math.round(ounces * GRAMS_PER_OUNCE);
}

export function formatWeight(grams: number): string {
  const ounces = grams / GRAMS_PER_OUNCE;
  if (ounces < 16) return `${Math.round(ounces * 10) / 10} oz`;
  return `${Math.round((ounces / 16) * 100) / 100} lb`;
}
