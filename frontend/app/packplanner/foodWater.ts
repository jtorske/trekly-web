import type { PackingCategory, PackingItem, Terrain } from "./packingList";

/** Configurable so these can be tuned later (e.g. higher target for difficult terrain). */
export const KCAL_PER_DAY_TARGET = 2800;
export const KCAL_DENSITY_PER_OZ = 125;

const MEAL_SPLIT: Array<{ name: string; frac: number }> = [
  { name: "Breakfast", frac: 0.2 },
  { name: "Lunch", frac: 0.25 },
  { name: "Dinner", frac: 0.3 },
  { name: "Snacks", frac: 0.25 },
];

export const WATER_LITERS_PER_DAY_MODERATE = 2.5;
export const WATER_LITERS_PER_DAY_DIFFICULT = 3.5;
export const FILTER_DAILY_CARRY_LITERS = 1.5;
export const LITERS_TO_LB = 2.2;

export function litersPerDayFor(terrain: Terrain, climateZone: string | null): number {
  const rugged = terrain === "difficult" || terrain === "extreme";
  const hotDry = climateZone === "desert";
  return rugged || hotDry ? WATER_LITERS_PER_DAY_DIFFICULT : WATER_LITERS_PER_DAY_MODERATE;
}

export interface FoodWaterParams {
  days: number;
  groupSize: number;
  terrain: Terrain;
  climateZone: string | null;
  filterAtCamp: boolean;
  /** Whether this trail has a known reliable water source to filter/resupply
   * from. Affects how much water gets carried when filterAtCamp is false. */
  canFilterAtCamp: boolean;
  kcalPerDayTarget?: number;
  kcalDensityPerOz?: number;
}

export interface FoodWaterResult {
  category: PackingCategory;
  totalKcal: number;
  totalFoodLb: number;
  totalWaterLiters: number;
  carryWaterLb: number;
}

let fwCounter = 0;
const fwId = (name: string) => {
  fwCounter += 1;
  return `foodwater-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${fwCounter}`;
};

/**
 * Builds the combined Food & Water category: calorie-driven meal weights
 * (not flat per-item guesses) plus a water line that reflects the
 * filter-at-camp vs. carry-all toggle. Pure/synchronous — no DB access.
 */
export function buildFoodWaterCategory(params: FoodWaterParams): FoodWaterResult {
  const { days, groupSize, terrain, climateZone, filterAtCamp, canFilterAtCamp } = params;
  const kcalPerDayTarget = params.kcalPerDayTarget ?? KCAL_PER_DAY_TARGET;
  const kcalDensityPerOz = params.kcalDensityPerOz ?? KCAL_DENSITY_PER_OZ;

  const kcalPerPersonTotal = kcalPerDayTarget * days;
  const foodOzPerPersonTotal = kcalPerPersonTotal / kcalDensityPerOz;
  const foodLbPerPersonTotal = foodOzPerPersonTotal / 16;

  const totalKcal = kcalPerPersonTotal * groupSize;
  const totalFoodLb = foodLbPerPersonTotal * groupSize;

  const items: PackingItem[] = MEAL_SPLIT.map(({ name, frac }) => {
    const kcalPerPersonForMeal = Math.round(kcalPerPersonTotal * frac);
    const kcalTotalForMeal = Math.round(totalKcal * frac);
    const weightLbPerServing = (foodLbPerPersonTotal * frac) / days;

    return {
      id: fwId(name),
      name,
      qty: days * groupSize,
      weightLb: weightLbPerServing,
      checked: false,
      shared: false,
      reason: `~${kcalTotalForMeal.toLocaleString()} kcal total (${kcalPerPersonForMeal.toLocaleString()} kcal/person) · ${(
        weightLbPerServing *
        days *
        groupSize
      ).toFixed(1)} lb`,
    };
  });

  const litersPerDay = litersPerDayFor(terrain, climateZone);
  const totalWaterLiters = litersPerDay * days * groupSize;
  // "Carry all" without a filter override doesn't need to mean the full
  // multi-day supply: if a reliable source exists somewhere on the trail,
  // only the leg to reach it (~first day) needs to be carried up front. Only
  // when there's truly no known source does the full trip volume apply.
  const firstLegLiters = litersPerDay * groupSize;
  const carryLiters = filterAtCamp
    ? FILTER_DAILY_CARRY_LITERS * groupSize
    : canFilterAtCamp
      ? firstLegLiters
      : totalWaterLiters;
  const carryWaterLb = carryLiters * LITERS_TO_LB;

  const waterReason = filterAtCamp
    ? `Filtering at camp — carrying ~${FILTER_DAILY_CARRY_LITERS}L/person between sources instead of ${totalWaterLiters.toFixed(1)}L total. Bring a filter.`
    : canFilterAtCamp
      ? `Carrying ${firstLegLiters.toFixed(1)}L to reach the first known water source (${litersPerDay}L/person/day) instead of the full ${totalWaterLiters.toFixed(1)}L trip supply — no filter carried, so refill there before continuing.`
      : `Carrying all ${totalWaterLiters.toFixed(1)}L for the trip (${litersPerDay}L/person/day × ${days} days) — no reliable water source is known on this trail.`;

  items.push({
    id: fwId("Water"),
    name: "Water",
    qty: 1,
    weightLb: carryWaterLb,
    checked: false,
    shared: false,
    reason: waterReason,
  });

  const category: PackingCategory = {
    id: "food-water",
    name: "Food & Water",
    summary: `${Math.round(totalKcal).toLocaleString()} kcal / ~${totalFoodLb.toFixed(1)} lb total food`,
    items,
  };

  return { category, totalKcal, totalFoodLb, totalWaterLiters, carryWaterLb };
}
