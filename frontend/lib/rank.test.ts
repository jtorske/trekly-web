import test from "node:test";
import assert from "node:assert/strict";
import { rankFor } from "./rank.ts";

test("rank thresholds match the backend's rank_for", () => {
  const cases: [number, number, string][] = [
    [0, 1, "Trailhead"],
    [1, 2, "Day Tripper"],
    [2, 2, "Day Tripper"],
    [3, 3, "Trail Regular"],
    [9, 3, "Trail Regular"],
    [10, 4, "Pathfinder"],
    [25, 5, "Backcountry Veteran"],
    [49, 5, "Backcountry Veteran"],
    [50, 6, "Trail Legend"],
    [400, 6, "Trail Legend"],
  ];
  for (const [hikes, level, title] of cases) assert.deepEqual(rankFor(hikes), { level, title }, `${hikes} hikes`);
});
