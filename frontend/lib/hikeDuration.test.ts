import test from "node:test";
import assert from "node:assert/strict";
import { fromMinutes, toMinutes } from "./hikeDuration.ts";

test("hours and minutes become minutes", () => {
  assert.equal(toMinutes("3", "30"), 210);
  assert.equal(toMinutes("2", ""), 120);
  assert.equal(toMinutes("", "45"), 45);
  assert.equal(toMinutes("", ""), null);
});

test("rejects nonsense and the API's limits", () => {
  for (const [h, m] of [["a", ""], ["1", "75"], ["", "5"], ["400", "0"], ["-1", ""], ["1.5", ""]]) {
    assert.equal(toMinutes(h, m), "invalid", `${h}:${m}`);
  }
});

test("round-trips", () => {
  assert.deepEqual(fromMinutes(215), { hours: "3", minutes: "35" });
  assert.deepEqual(fromMinutes(null), { hours: "", minutes: "" });
});
