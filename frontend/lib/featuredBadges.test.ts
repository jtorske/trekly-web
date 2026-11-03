import test from "node:test";
import assert from "node:assert/strict";
import { badgeKey, badgeName, earnedBadgeGroups, moveBadge, toggleBadge, type FeaturedBadge } from "./featuredBadges.ts";
import type { HikeLog } from "./hikeLogsApi.ts";
import type { TrailListItem } from "./trailsApi.ts";
import { milestone as made, sample } from "./milestones.fixtures.ts";

function log(name: string, region: string, nights = 0): HikeLog {
  return {
    trail: { id: name.toLowerCase().replace(/\W+/g, "-"), name, region, country_code: "CA", province_code: "AB", terrain: "moderate",
             typical_duration_nights: nights, distance_km: null } as TrailListItem,
    hiked_on: "2026-08-01",
    note: null,
    photo_path: null,
    logged_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };
}

const logs = [
  log("Sentinel Pass", "Banff National Park, AB"),
  log("Skyline Trail", "Jasper National Park, AB", 2),
  log("Lake Agnes", "Banff National Park, AB"),
];
const trail = (i: number): FeaturedBadge => ({ kind: "trail", trail: logs[i].trail });
const milestone = (id: string, title = "First steps"): FeaturedBadge => ({
  kind: "milestone",
  milestone: id,
  badge: { id, category: "getting-out", title, tier: "bronze", icon: id },
});

// The server's answer for these logs: what's earned, and what isn't.
const milestones = sample([
  made({ id: "first-hike", title: "First steps", earned: true }),
  made({ id: "trail-regular", title: "Trail regular", earned: false }),
  made({ id: "first-overnight", category: "nights", title: "Under the stars", earned: true }),
  made({ id: null, category: "seasons", title: "???", tier: null, secret: true, earned: false }),
]);

test("only earned badges: milestones first, then trails grouped by region", () => {
  const groups = earnedBadgeGroups(logs, milestones);
  assert.deepEqual(groups.map((g) => g.title), ["Milestones", "Banff National Park", "Jasper National Park"]);
  // Unearned ones, and hidden secrets, aren't offered.
  assert.deepEqual(groups[0].badges.map(badgeName), ["First steps", "Under the stars"]);
  assert.deepEqual(groups[1].badges.map(badgeName), ["Lake Agnes", "Sentinel Pass"]);
});

test("no hikes, no badges", () => {
  assert.deepEqual(earnedBadgeGroups([], sample([])), []);
  assert.deepEqual(earnedBadgeGroups([], null), []);
});

test("search matches trail, region and milestone names", () => {
  assert.deepEqual(earnedBadgeGroups(logs, milestones, "jasper").flatMap((g) => g.badges.map(badgeName)), ["Skyline Trail"]);
  assert.deepEqual(earnedBadgeGroups(logs, milestones, "AGNES").flatMap((g) => g.badges.map(badgeName)), ["Lake Agnes"]);
  assert.deepEqual(earnedBadgeGroups(logs, milestones, "stars").flatMap((g) => g.badges.map(badgeName)), ["Under the stars"]);
  assert.deepEqual(earnedBadgeGroups(logs, milestones, "nowhere"), []);
});

test("toggle adds and removes, and never a fourth", () => {
  let picked = toggleBadge([], trail(0));
  picked = toggleBadge(picked, milestone("first-hike"));
  picked = toggleBadge(picked, trail(1));
  assert.equal(picked.length, 3);
  assert.equal(toggleBadge(picked, trail(2)), picked, "a 4th is blocked");
  picked = toggleBadge(picked, milestone("first-hike"));
  assert.deepEqual(picked.map(badgeKey), [badgeKey(trail(0)), badgeKey(trail(1))]);
});

test("move reorders and clamps", () => {
  const picked = [trail(0), trail(1), milestone("first-hike")];
  assert.deepEqual(moveBadge(picked, 2, 0).map(badgeName), ["First steps", "Sentinel Pass", "Skyline Trail"]);
  assert.deepEqual(moveBadge(picked, 0, 1).map(badgeName), ["Skyline Trail", "Sentinel Pass", "First steps"]);
  assert.equal(moveBadge(picked, 0, -1), picked);
  assert.equal(moveBadge(picked, 2, 9), picked);
});
