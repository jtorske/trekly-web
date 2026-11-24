import test from "node:test";
import assert from "node:assert/strict";
import { SCENERY_OPTIONS, answerLabel, isoDate, nextStep, saturdayOf, toRequest, type PlannerAnswers } from "./guide.ts";
import { readFileSync } from "node:fs";

const SUMMER_TUESDAY = new Date(2027, 6, 6);
const WINTER_TUESDAY = new Date(2027, 0, 12);
const ctx = (overrides = {}) => ({ askExperience: false, homeProvince: null, today: SUMMER_TUESDAY, ...overrides });

function walk(answers: PlannerAnswers, context = ctx()) {
  const keys: string[] = [];
  let current = { ...answers };
  for (let step = nextStep(current, context); step; step = nextStep(current, context)) {
    keys.push(step.key);
    current = { ...current, [step.key]: step.choices[0].value === "pick" ? "2027-07-17" : step.choices[0].value };
  }
  return { keys, answers: current };
}

test("summer flow: five quick questions", () => {
  assert.deepEqual(walk({}).keys, ["when", "length", "difficulty", "where", "dog"]);
});

test("guests are asked their experience first", () => {
  assert.equal(walk({}, ctx({ askExperience: true })).keys[0], "experience");
});

test("winter dates ask the activity and about avalanche terrain, and drop overnight", () => {
  const { keys } = walk({}, ctx({ today: WINTER_TUESDAY }));
  assert.deepEqual(keys, ["when", "activity", "length", "difficulty", "where", "dog", "avalanche"]);
  const length = nextStep({ when: "this_weekend", activity: "snowshoe" }, ctx({ today: WINTER_TUESDAY }));
  assert.ok(length && !length.choices.some((c) => c.value === "overnight"));
});

test("shoulder months ask about avalanche terrain for alpine picks", () => {
  const november = ctx({ today: new Date(2026, 10, 24) });
  assert.deepEqual(walk({}, november).keys, ["when", "length", "difficulty", "where", "dog", "avalanche"]);
  assert.equal(toRequest({ when: "this_weekend" }, new Date(2026, 10, 24)).avoid_avalanche, true);
  assert.equal(toRequest({ when: "this_weekend", avalanche: "allow" }, new Date(2026, 10, 24)).avoid_avalanche, false);
});

test("home province comes first in Where", () => {
  const step = nextStep({ when: "this_weekend", length: "any", difficulty: "similar" }, ctx({ homeProvince: "ON" }));
  assert.equal(step?.choices[0].value, "ON");
  assert.equal(step?.choices.filter((c) => c.value === "ON").length, 1);
});

test("dog default puts Yes first", () => {
  const base = { when: "this_weekend", length: "any" as const, difficulty: "similar" as const, where: "anywhere" };
  assert.equal(nextStep(base, ctx({ dogByDefault: true }))?.choices[0].value, "yes");
  assert.equal(nextStep(base, ctx())?.choices[0].value, "no");
});

test("saturdayOf matches the backend's this weekend", () => {
  assert.equal(isoDate(saturdayOf(new Date(2026, 10, 24))), "2026-11-28");
  assert.equal(isoDate(saturdayOf(new Date(2026, 10, 28))), "2026-11-28");
  assert.equal(isoDate(saturdayOf(new Date(2026, 10, 29))), "2026-11-28");
  assert.equal(isoDate(saturdayOf(new Date(2026, 10, 24), 1)), "2026-12-05");
});

test("answers become a recommend request", () => {
  const request = toRequest(
    { when: "next_weekend", length: "half_day", difficulty: "push", where: "BC", dog: "yes" },
    SUMMER_TUESDAY, ["a"],
  );
  assert.deepEqual(request, {
    date: "2027-07-17", difficulty: "push", length: "half_day", province: "BC", dog: true, activity: "hike",
    avoid_avalanche: null, exclude_ids: ["a"], limit: 3, experience: null,
  });
  const winter = toRequest({ when: "this_weekend", activity: "snowshoe", length: "any", where: "anywhere",
                             avalanche: "allow" }, WINTER_TUESDAY);
  assert.equal(winter.date, "this_weekend");
  assert.equal(winter.length, null);
  assert.equal(winter.province, null);
  assert.equal(winter.activity, "snowshoe");
  assert.equal(winter.avoid_avalanche, false);
  assert.equal(toRequest({ when: "this_weekend" }, WINTER_TUESDAY).avoid_avalanche, true);
});

test("a picked date reads naturally", () => {
  const step = nextStep({}, ctx())!;
  assert.equal(answerLabel(step, "this_weekend"), "This weekend");
  assert.match(answerLabel(step, "2027-07-17"), /Saturday, July 17/);
});

test("scenery keys match the backend", () => {
  const python = readFileSync(new URL("../../backend/app/guide/estimate.py", import.meta.url), "utf8");
  const block = python.slice(python.indexOf("SCENERY = {"), python.indexOf("SCENERY_KEYS"));
  const keys = [...block.matchAll(/^\s+"(\w+)":/gm)].map((m) => m[1]);
  assert.deepEqual(SCENERY_OPTIONS.map((o) => o.value), keys);
});
