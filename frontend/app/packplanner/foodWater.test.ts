import test from "node:test";
import assert from "node:assert/strict";
import {
  buildFoodWaterCategory,
  FILTER_DAILY_CARRY_LITERS,
  WATER_LITERS_PER_DAY_MODERATE,
  LITERS_TO_LB,
} from "./foodWater.ts";

test("filterAtCamp carries only the daily filter amount, not the full trip supply", () => {
  const { carryWaterLb, totalWaterLiters } = buildFoodWaterCategory({
    days: 2,
    groupSize: 1,
    terrain: "easy",
    climateZone: null,
    filterAtCamp: true,
    canFilterAtCamp: true,
  });
  const expectedLb = FILTER_DAILY_CARRY_LITERS * LITERS_TO_LB;
  assert.equal(Math.round(carryWaterLb * 100) / 100, Math.round(expectedLb * 100) / 100);
  assert.ok(carryWaterLb < totalWaterLiters * LITERS_TO_LB);
});

test("carry-all with a known reliable source only charges the first day's leg, not the full trip", () => {
  const { carryWaterLb, totalWaterLiters } = buildFoodWaterCategory({
    days: 2,
    groupSize: 1,
    terrain: "easy",
    climateZone: null,
    filterAtCamp: false,
    canFilterAtCamp: true,
  });
  const expectedLb = WATER_LITERS_PER_DAY_MODERATE * LITERS_TO_LB;
  assert.equal(Math.round(carryWaterLb * 100) / 100, Math.round(expectedLb * 100) / 100);
  assert.ok(carryWaterLb < totalWaterLiters * LITERS_TO_LB);
});

test("carry-all with no known reliable source still charges the full multi-day supply", () => {
  const { carryWaterLb, totalWaterLiters } = buildFoodWaterCategory({
    days: 2,
    groupSize: 1,
    terrain: "easy",
    climateZone: null,
    filterAtCamp: false,
    canFilterAtCamp: false,
  });
  assert.equal(
    Math.round(carryWaterLb * 100) / 100,
    Math.round(totalWaterLiters * LITERS_TO_LB * 100) / 100,
  );
});

test("food/water category never includes a Water filter line — the caller owns showing/hiding it", () => {
  const { category } = buildFoodWaterCategory({
    days: 2,
    groupSize: 1,
    terrain: "easy",
    climateZone: null,
    filterAtCamp: false,
    canFilterAtCamp: true,
  });
  assert.ok(!category.items.some((item) => item.name === "Water filter"));
});
