import test from "node:test";
import assert from "node:assert/strict";
import { earnedSummary } from "./milestones.ts";
import { milestone } from "./milestones.fixtures.ts";

test("an earned milestone says how it was earned, in the past tense", () => {
  assert.equal(earnedSummary(milestone({ detail: "Hike {goal} trails", goal: 10 })), "Hiked 10 trails");
  assert.equal(earnedSummary(milestone({ detail: "Go on your first overnight trip", goal: null })), "Went on your first overnight trip");
  assert.equal(earnedSummary(milestone({ detail: "Spend {goal} nights out in total", goal: 10 })), "Spent 10 nights out in total");
});

test("distances follow the reader's units", () => {
  const century = milestone({ detail: "Hike {goal} in total", goal: 100, unit: "km" });
  assert.equal(earnedSummary(century), "Hiked 100 km in total");
  assert.equal(earnedSummary(century, "imperial"), "Hiked 62 mi in total");
});

test("an unknown verb keeps the requirement as written", () => {
  assert.equal(earnedSummary(milestone({ detail: "Paddle a lake", goal: null })), "Paddle a lake");
});
