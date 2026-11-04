import test from "node:test";
import assert from "node:assert/strict";
import {
  formatProblem,
  normalizeUsername,
  suggestionHint,
  usernameReady,
  type UsernameStatus,
} from "./usernames.ts";

test("formatProblem requires a username in the allowed format", () => {
  assert.equal(formatProblem(""), "Choose a username.");
  assert.equal(formatProblem("trail_jo"), null);
  for (const bad of ["ab", "has space", "dash-name", "x".repeat(31), "Upper"]) assert.ok(formatProblem(bad), bad);
  assert.equal(formatProblem(normalizeUsername("  Trail_Jo ")), null);
});

test("the username step can't go ahead without an available username", () => {
  const status = (state: UsernameStatus["state"]): UsernameStatus => ({ state, message: "" });
  for (const state of ["empty", "invalid", "checking", "taken"] as const) assert.equal(usernameReady(status(state)), false, state);
  assert.equal(usernameReady(status("available")), true);
  // API unreachable: the database trigger and the username step still apply.
  assert.equal(usernameReady(status("unchecked")), true);
  assert.equal(usernameReady(status("current")), true);
});

test("suggestionHint prefers the display name, then the email", () => {
  assert.equal(suggestionHint("Jordan Torske", "jt@example.com"), "Jordan Torske");
  assert.equal(suggestionHint("  ", "jt@example.com"), "jt@example.com");
  assert.equal(suggestionHint(null, null), "");
});
