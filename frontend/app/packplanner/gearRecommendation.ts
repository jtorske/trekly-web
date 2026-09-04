import { supabase } from "@/lib/supabaseClient";
import type { Season, Terrain } from "./packingList";

export interface VariantRecommendation {
  itemName: string;
  variantName: string;
  reason: string;
}

export interface PackingListItem {
  itemName: string;
  quantity: number;
  variantName?: string;
  reason?: string;
}

export interface PackingListCategory {
  category: string;
  items: PackingListItem[];
}

export interface GeneratedPackingList {
  categories: PackingListCategory[];
  conditions: {
    season: Season;
    avgLowC: number;
    avgHighC: number;
    isEstimate: boolean;
  };
}

interface RatedVariant {
  variant_name: string;
  min_temp_c: number;
  min_r_value: number | null;
}

/** Seasonal fallback ranges used when a trail has no recorded seasonal conditions. */
const SEASON_DEFAULT_RANGE_C: Record<Season, { low: number; high: number }> = {
  summer: { low: 5, high: 20 },
  spring: { low: -5, high: 10 },
  fall: { low: -5, high: 10 },
  winter: { low: -20, high: -5 },
};

/**
 * Pure matching logic, split out from the Supabase fetch so it can be unit
 * tested without a live client: pick the lightest/warmest-adequate variant
 * (highest min_temp_c at or below the target), falling back to the
 * warmest-rated variant overall if nothing is adequate.
 */
export function pickAdequateVariant(
  variants: RatedVariant[],
  targetTempC: number,
): { variant: RatedVariant; isFallback: boolean } {
  if (variants.length === 0) {
    throw new Error("No temperature-rated variants to choose from");
  }

  const sorted = [...variants].sort((a, b) => a.min_temp_c - b.min_temp_c);
  const adequate = sorted.filter((v) => v.min_temp_c <= targetTempC);

  if (adequate.length > 0) {
    const warmestAdequate = adequate.reduce((best, v) =>
      v.min_temp_c > best.min_temp_c ? v : best,
    );
    return { variant: warmestAdequate, isFallback: false };
  }

  // Nothing is rated cold enough for the target: fall back to the
  // warmest-rated variant available (lowest min_temp_c = most protective).
  return { variant: sorted[0], isFallback: true };
}

async function fetchRatedVariants(gearItemName: string): Promise<RatedVariant[]> {
  const { data: item, error: itemError } = await supabase
    .from("gear_items")
    .select("id")
    .eq("name", gearItemName)
    .maybeSingle();

  if (itemError) {
    throw new Error(`Failed to look up gear item "${gearItemName}": ${itemError.message}`);
  }
  if (!item) {
    throw new Error(`No gear item found named "${gearItemName}"`);
  }

  const { data: variants, error: variantsError } = await supabase
    .from("gear_variants")
    .select("variant_name, min_temp_c, min_r_value")
    .eq("gear_item_id", item.id);

  if (variantsError) {
    throw new Error(`Failed to fetch variants for "${gearItemName}": ${variantsError.message}`);
  }
  if (!variants || variants.length === 0) {
    throw new Error(`No gear variants defined for "${gearItemName}"`);
  }

  const rated: RatedVariant[] = variants
    .filter((v) => v.min_temp_c !== null)
    .map((v) => ({
      variant_name: v.variant_name,
      min_temp_c: Number(v.min_temp_c),
      min_r_value: v.min_r_value !== null ? Number(v.min_r_value) : null,
    }));

  if (rated.length === 0) {
    throw new Error(`Gear variants for "${gearItemName}" have no temperature ratings`);
  }

  return rated;
}

/**
 * Recommends a specific gear variant for graduated gear (sleeping bags,
 * insulated jackets, footwear, base layers, gloves) based on expected trip
 * lows. A safety buffer is subtracted from avgLowC before matching, since
 * backcountry lows tend to run colder than seasonal averages.
 */
export async function recommendVariant(
  gearItemName: string,
  avgLowC: number,
  terrainDifficulty: Terrain,
  safetyBufferC = 5,
): Promise<VariantRecommendation> {
  void terrainDifficulty; // reserved for future terrain-aware adjustments

  const rated = await fetchRatedVariants(gearItemName);
  const targetTempC = avgLowC - safetyBufferC;
  const { variant, isFallback } = pickAdequateVariant(rated, targetTempC);

  const reason = isFallback
    ? `${variant.variant_name} — the warmest option available; expected lows around ${avgLowC}°C may exceed its rating`
    : `${variant.variant_name} — expected lows around ${avgLowC}°C`;

  return { itemName: gearItemName, variantName: variant.variant_name, reason };
}

/**
 * Same variant-matching logic as recommendVariant, but for sleeping pads:
 * bumps to the next R-value tier up on difficult/extreme terrain, since cold
 * ground saps heat regardless of air temperature.
 */
export async function recommendSleepingPad(
  avgLowC: number,
  terrainDifficulty: Terrain,
  safetyBufferC = 5,
): Promise<VariantRecommendation> {
  const itemName = "Sleeping pad";
  const rated = await fetchRatedVariants(itemName);

  const targetTempC = avgLowC - safetyBufferC;
  const { variant: baseline, isFallback } = pickAdequateVariant(rated, targetTempC);

  const needsRBump = terrainDifficulty === "difficult" || terrainDifficulty === "extreme";
  let chosen = baseline;
  let bumped = false;

  if (needsRBump && baseline.min_r_value !== null) {
    const nextTier = rated
      .filter((v) => v.min_r_value !== null && v.min_r_value > baseline.min_r_value!)
      .sort((a, b) => a.min_r_value! - b.min_r_value!)[0];
    if (nextTier) {
      chosen = nextTier;
      bumped = true;
    }
  }

  const reason = isFallback
    ? `${chosen.variant_name} — the warmest pad available; expected lows around ${avgLowC}°C may exceed its rating`
    : bumped
      ? `${chosen.variant_name} — bumped up an R-value tier for ${terrainDifficulty} terrain (cold ground saps heat regardless of air temp)`
      : `${chosen.variant_name} — expected lows around ${avgLowC}°C`;

  return { itemName, variantName: chosen.variant_name, reason };
}

/**
 * Evaluates a gear_rules.quantity_formula string against known trip
 * variables. Only digits, arithmetic operators, and the whitelisted variable
 * names are permitted — anything else is rejected before evaluation.
 */
function evaluateQuantityFormula(
  formula: string,
  vars: { nights: number; days: number; groupSize: number },
): number {
  const substituted = formula
    .replace(/\bgroupSize\b/g, String(vars.groupSize))
    .replace(/\bnights\b/g, String(vars.nights))
    .replace(/\bdays\b/g, String(vars.days));

  if (!/^[0-9+\-*/().\s]*$/.test(substituted)) {
    throw new Error(`Unsafe or unrecognized quantity_formula: "${formula}"`);
  }

  const result = Function(`"use strict"; return (${substituted});`)() as unknown;
  if (typeof result !== "number" || !Number.isFinite(result)) {
    throw new Error(`quantity_formula "${formula}" did not evaluate to a finite number`);
  }
  return result;
}

/**
 * Builds the full categorized packing list for a trip: resolves graduated
 * gear (bag, pad, jacket, footwear, base layer, gloves) via temperature
 * matching, combines it with boolean gear_rules items, and groups everything
 * by gear category.
 */
export async function generatePackingList(
  trailId: string,
  season: Season,
  nights: number,
  groupSize: number,
  sharingTentStove: boolean,
): Promise<GeneratedPackingList> {
  const { data: trail, error: trailError } = await supabase
    .from("trails")
    .select("terrain_difficulty")
    .eq("id", trailId)
    .maybeSingle();

  if (trailError) {
    throw new Error(`Failed to load trail ${trailId}: ${trailError.message}`);
  }
  if (!trail) {
    throw new Error(`No trail found with id ${trailId}`);
  }
  const terrainDifficulty = trail.terrain_difficulty as Terrain;

  const { data: seasonalConditions, error: conditionsError } = await supabase
    .from("trail_seasonal_conditions")
    .select("avg_low_c, avg_high_c")
    .eq("trail_id", trailId)
    .eq("season", season)
    .maybeSingle();

  if (conditionsError) {
    throw new Error(
      `Failed to load seasonal conditions for trail ${trailId}: ${conditionsError.message}`,
    );
  }

  const isEstimate = !seasonalConditions;
  const fallbackRange = SEASON_DEFAULT_RANGE_C[season];
  const avgLowC = seasonalConditions ? Number(seasonalConditions.avg_low_c) : fallbackRange.low;
  const avgHighC = seasonalConditions
    ? Number(seasonalConditions.avg_high_c)
    : fallbackRange.high;

  const [sleepingBag, sleepingPad, insulatedJacket, footwear, baseLayer, gloves] =
    await Promise.all([
      recommendVariant("Sleeping bag", avgLowC, terrainDifficulty),
      recommendSleepingPad(avgLowC, terrainDifficulty),
      recommendVariant("Insulated jacket", avgLowC, terrainDifficulty),
      recommendVariant("Hiking footwear", avgLowC, terrainDifficulty),
      recommendVariant("Base layer top", avgLowC, terrainDifficulty),
      recommendVariant("Gloves", avgLowC, terrainDifficulty),
    ]);

  const { data: gearItems, error: gearItemsError } = await supabase
    .from("gear_items")
    .select("id, name, category, is_shareable");

  if (gearItemsError) {
    throw new Error(`Failed to load gear items: ${gearItemsError.message}`);
  }

  const itemById = new Map((gearItems ?? []).map((g) => [g.id, g]));
  const itemByName = new Map((gearItems ?? []).map((g) => [g.name, g]));

  const categoryMap = new Map<string, PackingListItem[]>();
  const addItem = (category: string, item: PackingListItem) => {
    const list = categoryMap.get(category) ?? [];
    list.push(item);
    categoryMap.set(category, list);
  };

  const graduated = [sleepingBag, sleepingPad, insulatedJacket, footwear, baseLayer, gloves];
  for (const rec of graduated) {
    const item = itemByName.get(rec.itemName);
    const category = item?.category ?? "gear";
    const quantity =
      item?.is_shareable && sharingTentStove ? 1 : Math.max(1, groupSize);
    addItem(category, {
      itemName: rec.itemName,
      quantity,
      variantName: rec.variantName,
      reason: rec.reason,
    });
  }

  const days = nights + 1;
  const { data: rules, error: rulesError } = await supabase.from("gear_rules").select(
    "gear_item_id, condition_terrain, condition_season, condition_min_nights, condition_min_temp_c, condition_max_temp_c, quantity_per_person, quantity_formula",
  );

  if (rulesError) {
    throw new Error(`Failed to load gear rules: ${rulesError.message}`);
  }

  for (const rule of rules ?? []) {
    if (rule.condition_terrain && rule.condition_terrain !== terrainDifficulty) continue;
    if (rule.condition_season && rule.condition_season !== season) continue;
    if (rule.condition_min_nights != null && nights < rule.condition_min_nights) continue;
    if (rule.condition_min_temp_c != null && avgLowC < Number(rule.condition_min_temp_c)) {
      continue;
    }
    if (rule.condition_max_temp_c != null && avgLowC > Number(rule.condition_max_temp_c)) {
      continue;
    }

    const item = itemById.get(rule.gear_item_id);
    if (!item) continue;

    const basePerPerson = rule.quantity_formula
      ? evaluateQuantityFormula(rule.quantity_formula, { nights, days, groupSize })
      : Number(rule.quantity_per_person ?? 1);

    const quantity =
      item.is_shareable && sharingTentStove
        ? Math.max(1, Math.round(basePerPerson))
        : Math.max(1, Math.round(basePerPerson * groupSize));

    addItem(item.category, { itemName: item.name, quantity });
  }

  const categories: PackingListCategory[] = Array.from(categoryMap.entries()).map(
    ([category, items]) => ({ category, items }),
  );

  return {
    categories,
    conditions: { season, avgLowC, avgHighC, isEstimate },
  };
}
