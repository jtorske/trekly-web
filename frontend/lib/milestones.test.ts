import test from "node:test";
import assert from "node:assert/strict";
import {
  categorySlug,
  earnedCount,
  milestoneDetail,
  milestoneSpreads,
  newlyEarned,
  progressFraction,
  progressLabel,
} from "./milestones.ts";
import { CATEGORIES, milestone, sample } from "./milestones.fixtures.ts";

const century = (km: number | null) =>
  milestone({
    id: "hundred-km",
    category: "distance",
    title: "Century",
    detail: "Hike {goal} in total",
    goal: 100,
    unit: "km",
    earned: km != null && km >= 100,
    progress: km != null && km > 0 && km < 100 ? { current: km, goal: 100, unit: "km", near: null } : null,
  });

test("details put the goal in the reader's units", () => {
  assert.equal(milestoneDetail(century(null)), "Hike 100 km in total");
  assert.equal(milestoneDetail(century(null), "imperial"), "Hike 62 mi in total");
  const everest = milestone({ detail: "Climb {goal} in total", goal: 8849, unit: "m" });
  assert.equal(milestoneDetail(everest), "Climb 8,849 m in total");
  assert.equal(milestoneDetail(everest, "imperial"), "Climb 29,032 ft in total");
  assert.equal(milestoneDetail(milestone({ detail: "Log {goal} hikes", goal: 10 })), "Log 10 hikes");
  assert.equal(milestoneDetail(milestone({ detail: "Hike a territory", goal: null })), "Hike a territory");
});

test("progress reads like 6 / 100 km, in whole units, never the goal before it's reached", () => {
  assert.equal(progressLabel(century(6)), "6 / 100 km");
  assert.equal(progressLabel(century(42.5), "imperial"), "26 / 62 mi");
  assert.equal(progressLabel(century(97)), "97 / 100 km");
  // 99.9 km is 62.07 mi: not earned, so it must not read "62 / 62 mi".
  assert.equal(progressLabel(century(99.9), "imperial"), "61 / 62 mi");
  assert.equal(progressLabel(century(99.9)), "99 / 100 km");
  assert.equal(progressLabel(century(null)), null, "no arc at zero");
  assert.equal(progressLabel(century(100)), null, "no arc once earned");
  const gain = milestone({ progress: { current: 8000, goal: 8849, unit: "m", near: null } });
  assert.equal(progressLabel(gain), "8,000 / 8,849 m");
  assert.equal(progressLabel(gain, "imperial"), "26,247 / 29,032 ft");
  assert.equal(progressLabel(milestone({ progress: { current: 4, goal: 10, unit: null, near: null } })), "4 / 10");
  const park = milestone({ progress: { current: 2, goal: 8, unit: null, near: "Jasper National Park, AB" } });
  assert.equal(progressLabel(park), "2 / 8 in Jasper National Park");
});

test("switching units never changes what's earned or the arc", () => {
  for (const km of [null, 6, 60, 96.6, 99.9, 100, 150]) {
    const m = century(km);
    assert.equal(progressFraction(m), m.earned ? 1 : km && km < 100 ? km / 100 : 0);
    assert.equal(progressLabel(m, "imperial") === null, progressLabel(m, "metric") === null);
  }
});

test("the milestones part: overview, a page per category, and Where to next? last", () => {
  const spreads = milestoneSpreads(sample());
  // The overview, 10 categories and the back page: 12 pages, 6 spreads, no blank needed.
  const pages = spreads.flatMap((s) => [s.left, s.right]);
  assert.equal(pages[0].kind, "overview");
  assert.equal(pages.at(-1)?.kind, "back");
  assert.equal(pages.length % 2, 0);
  assert.deepEqual(
    pages.flatMap((p) => (p.kind === "category" ? [p.category.id] : [])),
    CATEGORIES.map(([id]) => id),
  );
  assert.equal(spreads[0].slug, "milestones");
  assert.equal(spreads[1].slug, "milestones-nights");
  assert.equal(spreads[1].title, "Milestones: Nights out and Distance");
  assert.equal(new Set(spreads.map((s) => s.slug)).size, spreads.length, "slugs are unique");
});

test("an odd page count gets a blank page so Where to next? stays last", () => {
  const nine = sample([milestone()], CATEGORIES.slice(0, 9).map(([id, title]) => ({ id, title })));
  const pages = milestoneSpreads(nine).flatMap((s) => [s.left, s.right]);
  assert.deepEqual(pages.slice(-2).map((p) => p.kind), ["blank", "back"]);
  const ten = milestoneSpreads(sample()).flatMap((s) => [s.left, s.right]);
  assert.deepEqual(ten.slice(-2).map((p) => p.kind), ["category", "back"]);
});

test("a category's section, for links and toasts", () => {
  const data = sample();
  assert.equal(categorySlug(data, "getting-out"), "milestones");
  assert.equal(categorySlug(data, "distance"), "milestones-nights");
  assert.equal(categorySlug(data, "secret"), "milestones-secret");
  assert.equal(categorySlug(data, "nowhere"), "milestones");
});

test("newly earned: only against a known baseline, and never a hidden secret", () => {
  const data = sample([
    milestone({ id: "first-hike", earned: true }),
    milestone({ id: "trail-regular", earned: false }),
    milestone({ id: null, category: "secret", title: "???", secret: true, tier: null, earned: false }),
  ]);
  assert.deepEqual(newlyEarned(data, null), [], "no baseline yet: nothing toasts");
  assert.deepEqual(newlyEarned(data, new Set()).map((m) => m.id), ["first-hike"]);
  assert.deepEqual(newlyEarned(data, new Set(["first-hike"])), []);
  assert.equal(earnedCount(data), 1);
});
