import test from "node:test";
import assert from "node:assert/strict";
import { EDGE, GAP, floatingBox } from "./floatingBox.ts";

const viewport = { width: 1366, height: 768 };

test("drops below the field, at least 320px wide", () => {
  const box = floatingBox({ top: 300, bottom: 340, left: 120, width: 248 }, viewport);
  assert.deepEqual(box, { top: 340 + GAP, left: 120, width: 320, maxHeight: 352 });
});

test("shrinks to the room left below", () => {
  const box = floatingBox({ top: 400, bottom: 440, left: 120, width: 248 }, viewport);
  assert.equal(box.top, 440 + GAP);
  assert.equal(box.maxHeight, 768 - 440 - GAP - EDGE);
});

test("flips above when there's too little room below", () => {
  const box = floatingBox({ top: 640, bottom: 680, left: 120, width: 248 }, viewport, { topInset: 84 });
  assert.equal(box.top, undefined);
  assert.equal(box.bottom, 768 - 640 + GAP);
  assert.equal(box.maxHeight, 352);
});

test("stays inside a narrow viewport", () => {
  const box = floatingBox({ top: 200, bottom: 240, left: 16, width: 300 }, { width: 330, height: 844 });
  assert.equal(box.width, 330 - EDGE * 2);
  assert.equal(box.left, EDGE);
});
