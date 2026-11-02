/**
 * Pack weight maths for the gear page's weight summary. Weights always come
 * from item.weight.effective_g × quantity; formatting stays in lib/units.ts.
 */

import type { Carry, GearItem } from "@/lib/gearApi";
import { BIG_THREE_ZONES, PACK_CLASSES, WORN_BY_DEFAULT_SLOTS, type PackClass } from "./weightConfig.ts";
import { ZONES, slotForItem } from "./slots.ts";

/** The owner's choice, else the slot's default (boots are worn, the rest packed). */
export function carryOf(item: GearItem): Carry {
  return item.carry ?? (WORN_BY_DEFAULT_SLOTS.includes(slotForItem(item).key) ? "worn" : "packed");
}

export function isBigThree(zoneSlug: string): boolean {
  return (BIG_THREE_ZONES as readonly string[]).includes(zoneSlug);
}

export function packClassFor(baseGrams: number): PackClass {
  return PACK_CLASSES.find((band) => band.underGrams == null || baseGrams < band.underGrams)!;
}

export interface ZoneWeight {
  slug: string;
  label: string;
  grams: number;
  bigThree: boolean;
}

export interface PackSummary {
  /** Packed items with a known weight. */
  baseGrams: number;
  wornGrams: number;
  consumableGrams: number;
  /** Packed items with no weight: while any remain, base weight isn't known. */
  missingBase: number;
  /** Packed weight by zone, in ZONES order, zones with weight only. */
  zones: ZoneWeight[];
  bigThreeGrams: number;
  /** Null while some packed items have no weight. */
  packClass: PackClass | null;
}

export function packSummary(items: GearItem[]): PackSummary {
  const byZone = new Map<string, number>();
  let baseGrams = 0;
  let wornGrams = 0;
  let consumableGrams = 0;
  let missingBase = 0;
  for (const item of items) {
    const carry = carryOf(item);
    const grams = item.weight.effective_g == null ? null : item.weight.effective_g * item.quantity;
    if (carry === "worn") wornGrams += grams ?? 0;
    else if (carry === "consumable") consumableGrams += grams ?? 0;
    else if (grams == null) missingBase += 1;
    else {
      baseGrams += grams;
      const zone = slotForItem(item).zone;
      byZone.set(zone, (byZone.get(zone) ?? 0) + grams);
    }
  }
  const zones = ZONES.filter((zone) => (byZone.get(zone.slug) ?? 0) > 0).map((zone) => ({
    slug: zone.slug,
    label: zone.label,
    grams: byZone.get(zone.slug)!,
    bigThree: isBigThree(zone.slug),
  }));
  return {
    baseGrams,
    wornGrams,
    consumableGrams,
    missingBase,
    zones,
    bigThreeGrams: zones.filter((zone) => zone.bigThree).reduce((sum, zone) => sum + zone.grams, 0),
    packClass: missingBase > 0 || items.length === 0 ? null : packClassFor(baseGrams),
  };
}
