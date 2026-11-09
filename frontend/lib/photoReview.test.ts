import test from "node:test";
import assert from "node:assert/strict";
import { hasNewCandidates, hasNoCandidates, moveActive, reviewShortcut } from "./photoReview.ts";

const one = [{}];
const loaded = "2026-11-09T18:00:00Z";

test("never-reviewed trails with candidates are to review", () => {
  assert.equal(hasNewCandidates({ trail: { photo: null }, candidates: one, candidates_loaded_at: loaded, review: null }), true);
});

test("a No photo decision comes back only when newer candidates arrive", () => {
  const before = { decision: "rejected" as const, reviewed_at: "2026-10-28T10:00:00Z" };
  const after = { decision: "rejected" as const, reviewed_at: "2026-11-10T10:00:00Z" };
  assert.equal(hasNewCandidates({ trail: { photo: null }, candidates: one, candidates_loaded_at: loaded, review: before }), true);
  assert.equal(hasNewCandidates({ trail: { photo: null }, candidates: one, candidates_loaded_at: loaded, review: after }), false);
  // Older API responses without timestamps stay reviewed.
  assert.equal(hasNewCandidates({ trail: { photo: null }, candidates: one, review: { decision: "rejected" } }), false);
});

test("trails with a photo or no candidates are not to review", () => {
  const approved = { decision: "approved" as const, reviewed_at: "2026-10-28T10:00:00Z" };
  assert.equal(hasNewCandidates({ trail: { photo: {} }, candidates: one, candidates_loaded_at: loaded, review: approved }), false);
  assert.equal(hasNewCandidates({ trail: { photo: null }, candidates: [], candidates_loaded_at: loaded, review: null }), false);
  assert.equal(hasNoCandidates({ trail: { photo: null }, candidates: [], review: null }), true);
  assert.equal(hasNoCandidates({ trail: { photo: {} }, candidates: [], review: null }), false);
});

test("shortcut keys", () => {
  assert.deepEqual(reviewShortcut("1"), { kind: "pick", index: 0 });
  assert.deepEqual(reviewShortcut("5"), { kind: "pick", index: 4 });
  assert.equal(reviewShortcut("6"), null);
  assert.deepEqual(reviewShortcut("n"), { kind: "none" });
  assert.deepEqual(reviewShortcut("N"), { kind: "none" });
  assert.deepEqual(reviewShortcut("Enter"), { kind: "save" });
  assert.deepEqual(reviewShortcut("ArrowRight"), { kind: "move", by: 1 });
  assert.deepEqual(reviewShortcut("ArrowUp"), { kind: "move", by: -1 });
  assert.equal(reviewShortcut("a"), null);
});

test("moving the active trail crosses pages and stops at the ends", () => {
  assert.deepEqual(moveActive({ page: 0, index: 9 }, 1, 23, 10), { page: 1, index: 0 });
  assert.deepEqual(moveActive({ page: 1, index: 0 }, -1, 23, 10), { page: 0, index: 9 });
  assert.deepEqual(moveActive({ page: 0, index: 0 }, -1, 23, 10), { page: 0, index: 0 });
  assert.deepEqual(moveActive({ page: 2, index: 2 }, 1, 23, 10), { page: 2, index: 2 });
});
