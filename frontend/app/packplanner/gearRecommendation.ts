import { getSupabaseClient } from "@/lib/supabaseClient";
import type { Season, Terrain } from "./packingList";
import { gramsToLb, pickAdequateVariant, type RatedVariant } from "./gearMatching";

export { gramsToLb, pickAdequateVariant };

export interface VariantRecommendation {
  itemName: string;
  variantName: string;
  reason: string;
  /** The chosen variant's own weight in grams, when set on gear_variants. */
  weightG: number | null;
}

export interface PackingListItem {
  itemName: string;
  quantity: number;
  variantName?: string;
  reason?: string;
  /** Per-unit weight in pounds. Total display weight = weightLb * quantity,
   * computed by the caller — quantity is never folded into this value. */
  weightLb?: number;
  /** True when quantity is a single group-wide total rather than per-person. */
  shared: boolean;
}

export interface PackingListCategory {
  category: string;
  items: PackingListItem[];
}

export interface GeneratedPackingList {
  categories: PackingListCategory[];
  conditions: {
    season: Season;
    avgLowC: number | null;
    avgHighC: number | null;
    isEstimate: boolean;
    insufficientData: boolean;
    message?: string;
    climateZone: string | null;
    precipLikelihood: "low" | "moderate" | "high" | null;
    highWind: boolean;
  };
  /** Whether this trail has at least one linked campsite, as a rough proxy
   * for "you can plausibly filter water at camp instead of carrying it all." */
  canFilterAtCamp: boolean;
}

/**
 * Seasonal fallback ranges, branched by climate zone, used only when a trail
 * has no trail_seasonal_conditions row for the requested season. A climate
 * zone not listed here (or missing entirely) is NOT guessed at — the caller
 * gets insufficientData: true instead of a made-up number.
 */
const CLIMATE_SEASON_DEFAULTS_C: Record<string, Record<Season, { low: number; high: number }>> = {
  alpine: {
    spring: { low: -10, high: 5 },
    summer: { low: 2, high: 18 },
    fall: { low: -8, high: 8 },
    winter: { low: -20, high: -5 },
  },
  coastal_temperate: {
    spring: { low: 2, high: 14 },
    summer: { low: 10, high: 24 },
    fall: { low: 2, high: 14 },
    winter: { low: -2, high: 8 },
  },
  desert: {
    spring: { low: 5, high: 24 },
    summer: { low: 15, high: 38 },
    fall: { low: 5, high: 24 },
    winter: { low: -2, high: 16 },
  },
  temperate: {
    spring: { low: -2, high: 12 },
    summer: { low: 12, high: 26 },
    fall: { low: 0, high: 14 },
    winter: { low: -8, high: 4 },
  },
};

async function fetchRatedVariants(gearItemName: string): Promise<RatedVariant[]> {
  const supabase = getSupabaseClient();

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
    .select("variant_name, min_temp_c, min_r_value, weight_g")
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
      weight_g: v.weight_g !== null ? Number(v.weight_g) : null,
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

  return {
    itemName: gearItemName,
    variantName: variant.variant_name,
    reason,
    weightG: variant.weight_g,
  };
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

  return { itemName, variantName: chosen.variant_name, reason, weightG: chosen.weight_g };
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
 * matching, combines it with boolean gear_rules items (including baseline
 * essentials and region/wind/precip-gated extras), and groups everything by
 * gear category.
 */
export async function generatePackingList(
  trailId: string,
  season: Season,
  nights: number,
  groupSize: number,
  sharingTentStove: boolean,
): Promise<GeneratedPackingList> {
  const supabase = getSupabaseClient();

  const { data: trail, error: trailError } = await supabase
    .from("trails")
    .select("terrain_difficulty, climate_zone")
    .eq("id", trailId)
    .maybeSingle();

  if (trailError) {
    throw new Error(`Failed to load trail ${trailId}: ${trailError.message}`);
  }
  if (!trail) {
    throw new Error(`No trail found with id ${trailId}`);
  }
  const terrainDifficulty = trail.terrain_difficulty as Terrain;
  const climateZone: string | null = trail.climate_zone ?? null;

  const { data: seasonalConditions, error: conditionsError } = await supabase
    .from("trail_seasonal_conditions")
    .select("avg_low_c, avg_high_c, precip_likelihood, high_wind")
    .eq("trail_id", trailId)
    .eq("season", season)
    .maybeSingle();

  if (conditionsError) {
    throw new Error(
      `Failed to load seasonal conditions for trail ${trailId}: ${conditionsError.message}`,
    );
  }

  let avgLowC: number | null;
  let avgHighC: number | null;
  let isEstimate: boolean;
  let insufficientData = false;
  let message: string | undefined;
  let precipLikelihood: "low" | "moderate" | "high" | null = null;
  let highWind = false;

  if (seasonalConditions) {
    avgLowC = Number(seasonalConditions.avg_low_c);
    avgHighC = Number(seasonalConditions.avg_high_c);
    isEstimate = false;
    precipLikelihood = seasonalConditions.precip_likelihood ?? null;
    highWind = Boolean(seasonalConditions.high_wind);
  } else {
    const zoneDefaults = climateZone ? CLIMATE_SEASON_DEFAULTS_C[climateZone] : undefined;
    if (zoneDefaults) {
      avgLowC = zoneDefaults[season].low;
      avgHighC = zoneDefaults[season].high;
      isEstimate = true;
    } else {
      avgLowC = null;
      avgHighC = null;
      isEstimate = true;
      insufficientData = true;
      message = climateZone
        ? `We don't have a temperature model for the "${climateZone}" climate zone yet — please confirm expected lows/highs yourself before relying on the sleep/clothing recommendations below.`
        : "This trail has no recorded seasonal data or climate zone, so we can't estimate expected temperatures — please confirm expected lows/highs yourself before relying on the sleep/clothing recommendations below.";
    }
  }

  const { count: campsiteCount, error: campsiteError } = await supabase
    .from("campsites")
    .select("id", { count: "exact", head: true })
    .eq("trail_id", trailId);

  if (campsiteError) {
    throw new Error(`Failed to check campsites for trail ${trailId}: ${campsiteError.message}`);
  }
  const canFilterAtCamp = (campsiteCount ?? 0) > 0;

  const { data: gearItems, error: gearItemsError } = await supabase
    .from("gear_items")
    .select("id, name, category, is_shareable, weight_g");

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

  if (!insufficientData && avgLowC !== null) {
    const [sleepingBag, sleepingPad, insulatedJacket, footwear, baseLayer, gloves] =
      await Promise.all([
        recommendVariant("Sleeping bag", avgLowC, terrainDifficulty),
        recommendSleepingPad(avgLowC, terrainDifficulty),
        recommendVariant("Insulated jacket", avgLowC, terrainDifficulty),
        recommendVariant("Hiking footwear", avgLowC, terrainDifficulty),
        recommendVariant("Base layer top", avgLowC, terrainDifficulty),
        recommendVariant("Gloves", avgLowC, terrainDifficulty),
      ]);

    const graduated = [sleepingBag, sleepingPad, insulatedJacket, footwear, baseLayer, gloves];
    for (const rec of graduated) {
      const item = itemByName.get(rec.itemName);
      const category = item?.category ?? "gear";
      const shared = Boolean(item?.is_shareable) && sharingTentStove;
      const quantity = shared ? 1 : Math.max(1, groupSize);
      // Quantity multiplication happens once, here, entirely in pounds —
      // weightLb is per-unit and is never itself scaled by quantity.
      // Prefer the chosen variant's own weight (a winter bag weighs more
      // than a summer one) — only fall back to the base item weight if this
      // particular variant has no weight_g set.
      const gramsForItem = rec.weightG ?? item?.weight_g ?? null;
      const weightLb = gramsForItem ? gramsToLb(gramsForItem) : undefined;
      addItem(category, {
        itemName: rec.itemName,
        quantity,
        variantName: rec.variantName,
        reason: rec.reason,
        weightLb,
        shared,
      });
    }
  }

  const days = nights + 1;
  const { data: rules, error: rulesError } = await supabase.from("gear_rules").select(
    "gear_item_id, condition_terrain, condition_season, condition_min_nights, condition_min_temp_c, condition_max_temp_c, quantity_per_person, quantity_formula, condition_climate_zone, condition_requires_high_precip, condition_requires_high_wind",
  );

  if (rulesError) {
    throw new Error(`Failed to load gear rules: ${rulesError.message}`);
  }

  for (const rule of rules ?? []) {
    if (rule.condition_terrain && rule.condition_terrain !== terrainDifficulty) continue;
    if (rule.condition_season && rule.condition_season !== season) continue;
    if (rule.condition_min_nights != null && nights < rule.condition_min_nights) continue;
    if (rule.condition_climate_zone && rule.condition_climate_zone !== climateZone) continue;
    if (rule.condition_requires_high_wind && !highWind) continue;
    if (rule.condition_requires_high_precip && precipLikelihood !== "high") continue;

    if (rule.condition_min_temp_c != null || rule.condition_max_temp_c != null) {
      // Temperature-gated rule, but we have no temperature to evaluate it
      // against — skip rather than guess.
      if (avgLowC === null) continue;
      if (rule.condition_min_temp_c != null && avgLowC < Number(rule.condition_min_temp_c)) {
        continue;
      }
      if (rule.condition_max_temp_c != null && avgLowC > Number(rule.condition_max_temp_c)) {
        continue;
      }
    }

    const item = itemById.get(rule.gear_item_id);
    if (!item) continue;

    const basePerPerson = rule.quantity_formula
      ? evaluateQuantityFormula(rule.quantity_formula, { nights, days, groupSize })
      : Number(rule.quantity_per_person ?? 1);

    const shared = Boolean(item.is_shareable) && sharingTentStove;
    const quantity = shared
      ? Math.max(1, Math.round(basePerPerson))
      : Math.max(1, Math.round(basePerPerson * groupSize));

    addItem(item.category, {
      itemName: item.name,
      quantity,
      weightLb: item.weight_g ? gramsToLb(item.weight_g) : undefined,
      shared,
    });
  }

  const categories: PackingListCategory[] = Array.from(categoryMap.entries()).map(
    ([category, items]) => ({ category, items }),
  );

  return {
    categories,
    conditions: {
      season,
      avgLowC,
      avgHighC,
      isEstimate,
      insufficientData,
      message,
      climateZone,
      precipLikelihood,
      highWind,
    },
    canFilterAtCamp,
  };
}
