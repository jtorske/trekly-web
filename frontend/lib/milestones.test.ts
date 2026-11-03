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
  // The overview, 11 categories, a blank and the back page: 14 pages, 7 spreads.
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
  assert.equal(spreads.length, 7);
  assert.deepEqual(pages.slice(-2).map((p) => p.kind), ["blank", "back"]);
  assert.equal(new Set(spreads.map((s) => s.slug)).size, spreads.length, "slugs are unique");
});

test("an odd page count gets a blank page so Where to next? stays last", () => {
  const nine = sample([milestone()], CATEGORIES.slice(0, 9).map(([id, title]) => ({ id, title })));
  const pages = milestoneSpreads(nine).flatMap((s) => [s.left, s.right]);
  assert.deepEqual(pages.slice(-2).map((p) => p.kind), ["blank", "back"]);
  const ten = milestoneSpreads(sample([milestone()], CATEGORIES.slice(0, 10).map(([id, title]) => ({ id, title }))));
  assert.deepEqual(ten.flatMap((s) => [s.left, s.right]).slice(-2).map((p) => p.kind), ["category", "back"]);
});

test("a category's section, for links and toasts", () => {
  const data = sample();
  assert.equal(categorySlug(data, "getting-out"), "milestones");
  assert.equal(categorySlug(data, "distance"), "milestones-nights");
  assert.equal(categorySlug(data, "gear"), "milestones-planning");
  assert.equal(categorySlug(data, "routes"), "milestones-difficulty");
  assert.equal(categorySlug(data, "nowhere"), "milestones");
});

test("newly earned: only against a known baseline, and never a hidden secret", () => {
  const data = sample([
    milestone({ id: "first-hike", earned: true }),
    milestone({ id: "trail-regular", earned: false }),
    milestone({ id: null, category: "seasons", title: "???", detail: "Celebrate the true north", secret: true, tier: null, earned: false }),
  ]);
  assert.deepEqual(newlyEarned(data, null), [], "no baseline yet: nothing toasts");
  assert.deepEqual(newlyEarned(data, new Set()).map((m) => m.id), ["first-hike"]);
  assert.deepEqual(newlyEarned(data, new Set(["first-hike"])), []);
  assert.equal(earnedCount(data), 1);
});

test("a hidden secret shows only ??? and its hint, in its own category", () => {
  const hidden = milestone({ id: null, category: "seasons", title: "???", detail: "Celebrate the true north", goal: null, secret: true, tier: null, icon: "secret", earned: false });
  assert.equal(milestoneDetail(hidden), "Celebrate the true north");
  assert.equal(progressLabel(hidden), null);
  assert.equal(progressFraction(hidden), 0);
  const data = sample([hidden]);
  assert.deepEqual(newlyEarned(data, new Set()), []);
  const page = milestoneSpreads(data).flatMap((s) => [s.left, s.right]).find((p) => p.kind === "category" && p.category.id === "seasons");
  assert.ok(page && page.kind === "category" && page.milestones[0].title === "???");
});

test("a milestone waiting on trail data has no progress to show", () => {
  const waiting = milestone({ id: "long-hauler", detail: "Hike {goal} in total", goal: 250, unit: "km", needs_data: true, progress: null });
  assert.equal(milestoneDetail(waiting), "Hike 250 km in total");
  assert.equal(progressLabel(waiting), null);
  assert.equal(progressFraction(waiting), 0);
});

test("a category longer than a page carries on under the same heading", () => {
  const exploration = Array.from({ length: 10 }, (_, i) => milestone({ id: `e${i}`, category: "exploration", earned: i < 4 }));
  const seasons = Array.from({ length: 9 }, (_, i) => milestone({ id: `s${i}`, category: "seasons" }));
  const data = sample([milestone(), ...exploration, ...seasons]);
  const spreads = milestoneSpreads(data);
  const pages = spreads.flatMap((s) => [s.left, s.right]);
  const of = (id: string) => pages.filter((p) => p.kind === "category" && p.category.id === id);
  const parts = (id: string) => of(id).map((p) => (p.kind === "category" ? [p.milestones.length, p.continued] : null));
  assert.deepEqual(parts("exploration"), [[6, false], [4, true]]);
  assert.deepEqual(parts("seasons"), [[6, false], [3, true]]);
  assert.deepEqual(parts("gear"), [[0, false]], "an empty category still gets its page");
  assert.ok(pages.every((p) => p.kind !== "category" || p.milestones.length <= 6));
  // Every milestone is on exactly one page, in order.
  assert.deepEqual(pages.flatMap((p) => (p.kind === "category" ? p.milestones.map((m) => m.id) : [])), data.milestones.map((m) => m.id));
  // Links go to a category's first page; slugs stay unique; Where to next? is still last.
  assert.equal(categorySlug(data, "exploration"), spreads.find((s) => s.left === of("exploration")[0] || s.right === of("exploration")[0])?.slug);
  assert.equal(new Set(spreads.map((s) => s.slug)).size, spreads.length);
  assert.equal(pages.at(-1)?.kind, "back");
  assert.equal(pages.length % 2, 0);
  assert.equal(spreads.filter((s) => s.title.includes("Exploration")).length, 2);
});
