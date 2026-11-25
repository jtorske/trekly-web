import test from "node:test";
import assert from "node:assert/strict";
import {
  SEASON_MODE_STORAGE_KEY,
  choiceToStore,
  parseStoredMode,
  readStoredMode,
  resolveSeasonMode,
  writeStoredMode,
} from "./seasonMode.ts";

test("defaults to the current season until they choose", () => {
  assert.equal(resolveSeasonMode(null, "winter"), "winter");
  assert.equal(resolveSeasonMode(undefined, "summer"), "summer");
  assert.equal(resolveSeasonMode(null, null), null);
});

test("their own choice wins over the season", () => {
  assert.equal(resolveSeasonMode("summer", "winter"), "summer");
});

test("choosing the current season stores nothing, so it follows the season later", () => {
  assert.equal(choiceToStore("winter", "winter"), null);
  assert.equal(choiceToStore("summer", "winter"), "summer");
  assert.equal(choiceToStore("winter", null), "winter");
});

test("only summer and winter are read back", () => {
  assert.equal(parseStoredMode("winter"), "winter");
  assert.equal(parseStoredMode("fall"), null);
  assert.equal(parseStoredMode(null), null);
});

test("storage round trip, and blocked storage doesn't throw", () => {
  const data = new Map<string, string>();
  const storage = {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
  writeStoredMode(storage, "summer");
  assert.equal(data.get(SEASON_MODE_STORAGE_KEY), "summer");
  assert.equal(readStoredMode(storage), "summer");
  writeStoredMode(storage, null);
  assert.equal(readStoredMode(storage), null);
  const blocked = {
    getItem: () => { throw new Error("blocked"); },
    setItem: () => { throw new Error("blocked"); },
    removeItem: () => { throw new Error("blocked"); },
  };
  assert.equal(readStoredMode(blocked), null);
  assert.doesNotThrow(() => writeStoredMode(blocked, "winter"));
});
