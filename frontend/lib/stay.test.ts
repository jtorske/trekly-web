import test from "node:test";
import assert from "node:assert/strict";
import { addDays, canAlert, sentence, defaultStay, formatStay, localToday, stayFromParams, stayParams } from "./stay.ts";

test("adding days crosses months and years in UTC", () => {
  assert.equal(addDays("2026-10-30", 3), "2026-11-02");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
});

test("today is the local calendar date", () => {
  assert.equal(localToday(new Date(2026, 9, 15, 23, 30)), "2026-10-15");
});

test("default stay is two weeks out with the trail's typical length", () => {
  assert.deepEqual(defaultStay("2026-10-15", 3), { start: "2026-10-29", nights: 3, party: 2 });
  assert.equal(defaultStay("2026-10-15", 0).nights, 1);
  assert.equal(defaultStay("2026-10-15", 30).nights, 14);
});

test("stays round-trip through the URL and invalid ones are dropped", () => {
  const stay = { start: "2026-10-20", nights: 3, party: 4 };
  assert.deepEqual(stayFromParams(new URLSearchParams(stayParams(stay)), "2026-10-15"), stay);
  const today = "2026-10-15";
  assert.equal(stayFromParams(new URLSearchParams({ start: "2026-10-14", nights: "2" }), today), null);
  assert.equal(stayFromParams(new URLSearchParams({ start: "2026-10-20", nights: "15" }), today), null);
  assert.equal(stayFromParams(new URLSearchParams({ start: "oct 20", nights: "2" }), today), null);
  assert.equal(stayFromParams(new URLSearchParams({ start: "2026-10-20" }), today), null);
  assert.equal(stayFromParams(new URLSearchParams({ start: "2026-10-20", nights: "2", party: "99" }), today)?.party, 2);
});

test("stay label ends on the morning you leave", () => {
  assert.equal(formatStay("2026-10-20", 2), "Tue, Oct 20 – Thu, Oct 22 · 2 nights");
  assert.equal(formatStay("2026-10-20", 1), "Tue, Oct 20 – Wed, Oct 21 · 1 night");
});

test("sentences don't get a second full stop", () => {
  assert.equal(sentence("checked at 2:41 p.m."), "checked at 2:41 p.m.");
  assert.equal(sentence("checked at 14:41"), "checked at 14:41.");
});

test("alerts are offered only when a stay could open up", () => {
  assert.equal(canAlert("full"), true);
  assert.equal(canAlert("partial"), true);
  assert.equal(canAlert("not_released"), true);
  assert.equal(canAlert("available"), false);
  assert.equal(canAlert("closed"), false);
  assert.equal(canAlert("unknown"), false);
});
