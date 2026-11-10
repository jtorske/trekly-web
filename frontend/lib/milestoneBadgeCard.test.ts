import test from "node:test";
import assert from "node:assert/strict";
import { badgeMilestone, categorySlug, milestoneSpreads, milestoneDetail, milestoneSlug, shortDay, theirEarnedWhen, viewerStanding } from "./milestones.ts";
import { milestone, sample } from "./milestones.fixtures.ts";

const day = (d: string) => `<${d}>`;
const provinces = {
  id: "divide-crosser",
  category: "exploration",
  title: "Divide crosser",
  tier: "bronze" as const,
  icon: "divide",
  detail: "Hike in both Alberta and British Columbia",
  goal: null,
  unit: null,
  secret: false,
  earned_on: "2026-10-30",
  earned_with: null,
};

test("someone's badge reads as an earned milestone with its requirement", () => {
  const m = badgeMilestone(provinces);
  assert.equal(m.earned, true);
  assert.equal(m.tier, "bronze");
  assert.equal(milestoneDetail(m), "Hike in both Alberta and British Columbia");
  assert.equal(m.progress, null);
  // An older payload without the card fields still draws.
  assert.equal(badgeMilestone({ id: "x", category: "c", title: "X", tier: "gold", icon: "i" }).detail, "");
});

test("when they earned it: a date, past hikes, or nothing while dates are hidden", () => {
  assert.equal(theirEarnedWhen(provinces, day), "Earned <2026-10-30>");
  assert.equal(theirEarnedWhen({ earned_on: null, earned_with: "past_hikes" }, day), "Earned from past hikes");
  assert.equal(theirEarnedWhen({ earned_on: null, earned_with: null }, day), null);
});

test("the viewer's own standing", () => {
  const earned = sample([milestone({ id: "divide-crosser", earned: true, earned_on: "2026-10-30" })]);
  assert.deepEqual(viewerStanding("divide-crosser", earned, day), { text: "You: earned it on <2026-10-30>", secret: false });
  const joined = sample([milestone({ id: "divide-crosser", earned: true, earned_with: "joining" })]);
  assert.equal(viewerStanding("divide-crosser", joined, day).text, "You: earned it when you joined");

  const partway = sample([
    milestone({ id: "divide-crosser", earned: false, progress: { current: 1, goal: 2, unit: null, near: null } }),
  ]);
  assert.equal(viewerStanding("divide-crosser", partway, day).text, "You: 1 of 2");
  const km = sample([
    milestone({ id: "hundred-km", goal: 100, unit: "km", progress: { current: 6, goal: 100, unit: "km", near: null } }),
  ]);
  assert.equal(viewerStanding("hundred-km", km, day).text, "You: 6 of 100 km");
  assert.equal(viewerStanding("hundred-km", km, day, "imperial").text, "You: 3 of 62 mi");

  const none = sample([milestone({ id: "divide-crosser" })]);
  assert.equal(viewerStanding("divide-crosser", none, day).text, "You: not earned yet");
  const waiting = sample([
    milestone({ id: "divide-crosser", needs_data: true, progress: { current: 1, goal: 2, unit: null, near: null } }),
  ]);
  assert.equal(viewerStanding("divide-crosser", waiting, day).text, "You: not earned yet");
});

test("a secret the viewer hasn't earned stays secret", () => {
  // The server sends an unearned secret with no id and "???".
  const mine = sample([milestone({ id: null, title: "???", secret: true, detail: "Hint: think dark" })]);
  assert.deepEqual(viewerStanding("night-owl", mine, day), { text: "Secret milestone", secret: true });
  const earned = sample([milestone({ id: "night-owl", secret: true, earned: true, earned_on: "2026-09-01" })]);
  assert.equal(viewerStanding("night-owl", earned, day).text, "You: earned it on <2026-09-01>");
});

test("the journal section for a medal, even on a category's second page", () => {
  const many = Array.from({ length: 8 }, (_, i) => milestone({ id: `e${i}`, category: "exploration" }));
  const data = sample([milestone(), ...many]);
  assert.equal(milestoneSlug(data, "e0"), categorySlug(data, "exploration"));
  // The seventh and eighth carry on over the page.
  const second = milestoneSpreads(data).find((s) => s.slug === milestoneSlug(data, "e7"))!;
  const pages = [second.left, second.right].filter((p) => p.kind === "category");
  assert.ok(pages.some((p) => p.kind === "category" && p.continued && p.milestones.some((m) => m.id === "e7")));
  assert.equal(milestoneSlug(data, "missing"), "milestones");
});

test("short days drop this year", () => {
  const now = new Date(2026, 10, 9);
  assert.equal(shortDay("2026-10-30", now), "Oct 30");
  assert.equal(shortDay("2025-10-30", now), "Oct 30, 2025");
});
