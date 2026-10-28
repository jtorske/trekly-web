import test from "node:test";
import assert from "node:assert/strict";
import { progressLabel, shouldCelebrate, type MyRank } from "./rank.ts";

const rookie = { level: 1, title: "Trailhead Rookie" };
const tripper = { level: 2, title: "Day Tripper" };

test("a rank-up celebrates only right after logging a hike", () => {
  assert.equal(shouldCelebrate(rookie, tripper, "hike-added"), true);
  // Never on page load, even if the rank went up since the last visit.
  assert.equal(shouldCelebrate(rookie, tripper, "load"), false);
  assert.equal(shouldCelebrate(null, tripper, "hike-added"), false);
  // Edits and deletions never celebrate, and nor does staying put or going down.
  assert.equal(shouldCelebrate(rookie, tripper, "hike-changed"), false);
  assert.equal(shouldCelebrate(tripper, tripper, "hike-added"), false);
  assert.equal(shouldCelebrate(tripper, rookie, "hike-added"), false);
});

test("the progress label names the next rank, or says it's the top", () => {
  const mine: MyRank = {
    points: 120,
    rank: { ...tripper, threshold: 50 },
    next: { level: 3, title: "Switchback Regular", threshold: 250 },
    progress: 0.35,
    breakdown: { trails: 60, nights: 0, regions: 30, milestones: 25 },
  };
  assert.equal(progressLabel(mine), "120 / 250 points to Switchback Regular");
  assert.equal(progressLabel({ ...mine, points: 3100, next: null }), "3,100 points · the top rank");
});
