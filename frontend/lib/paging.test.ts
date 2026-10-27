import test from "node:test";
import assert from "node:assert/strict";
import { pageOf } from "./paging.ts";

const items = Array.from({ length: 23 }, (_, i) => i);

test("slices pages of the given size", () => {
  assert.deepEqual(pageOf(items, 0, 10), { items: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], page: 0, pages: 3 });
  assert.deepEqual(pageOf(items, 2, 10), { items: [20, 21, 22], page: 2, pages: 3 });
});

test("clamps a page that no longer exists (the list shrank after reviewing)", () => {
  assert.deepEqual(pageOf(items.slice(0, 15), 2, 10), { items: [10, 11, 12, 13, 14], page: 1, pages: 2 });
  assert.equal(pageOf(items, -1, 10).page, 0);
});

test("an empty list is one empty page", () => {
  assert.deepEqual(pageOf([], 3, 10), { items: [], page: 0, pages: 1 });
});
