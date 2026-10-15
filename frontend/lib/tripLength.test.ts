import test from "node:test";
import assert from "node:assert/strict";
import { tripLengthLabel } from "./tripLength.ts";

test("trip length labels", () => {
  assert.equal(tripLengthLabel(0), "Day hike");
  assert.equal(tripLengthLabel(1), "1 night");
  assert.equal(tripLengthLabel(4), "4 nights");
});
