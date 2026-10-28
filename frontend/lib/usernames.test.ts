import test from "node:test";
import assert from "node:assert/strict";
import {
  formatProblem,
  normalizeUsername,
  pathIsOpen,
  signUpMetadata,
  suggestionHint,
  usernameGate,
  usernameReady,
  type UsernameStatus,
} from "./usernames.ts";

const signedIn = {
  authStatus: "signedIn" as const,
  pathname: "/journal",
  profileLoading: false,
  profileError: null,
  username: null,
  knownToHaveUsername: false,
};

test("formatProblem requires a username in the allowed format", () => {
  assert.equal(formatProblem(""), "Choose a username.");
  assert.equal(formatProblem("trail_jo"), null);
  for (const bad of ["ab", "has space", "dash-name", "x".repeat(31), "Upper"]) assert.ok(formatProblem(bad), bad);
  assert.equal(formatProblem(normalizeUsername("  Trail_Jo ")), null);
});

test("sign-up can't go ahead without an available username", () => {
  const status = (state: UsernameStatus["state"]): UsernameStatus => ({ state, message: "" });
  for (const state of ["empty", "invalid", "checking", "taken"] as const) assert.equal(usernameReady(status(state)), false, state);
  assert.equal(usernameReady(status("available")), true);
  // API unreachable: the database trigger and the username step still apply.
  assert.equal(usernameReady(status("unchecked")), true);
  assert.equal(usernameReady(status("current")), true);
});

test("sign-up metadata always carries the username, normalized", () => {
  assert.deepEqual(signUpMetadata("", " Trail_Jo "), { username: "trail_jo" });
  assert.deepEqual(signUpMetadata("  Jo Hiker ", "trail_jo"), { username: "trail_jo", display_name: "Jo Hiker" });
});

test("suggestionHint prefers the display name, then the email", () => {
  assert.equal(suggestionHint("Jordan Torske", "jt@example.com"), "Jordan Torske");
  assert.equal(suggestionHint("  ", "jt@example.com"), "jt@example.com");
  assert.equal(suggestionHint(null, null), "");
});

test("a signed-in user without a username can't reach app pages", () => {
  for (const pathname of ["/", "/journal", "/gear", "/profile", "/plans/new", "/u/someone", "/trails/abc"]) {
    assert.equal(usernameGate({ ...signedIn, pathname }), "choose", pathname);
  }
});

test("an OAuth user fresh from the callback is asked once they land on an app page", () => {
  assert.equal(usernameGate({ ...signedIn, pathname: "/auth/callback" }), "pass");
  assert.equal(usernameGate({ ...signedIn, pathname: "/" }), "choose");
});

test("the legal pages and sign-in plumbing stay open", () => {
  for (const pathname of ["/privacy", "/terms", "/auth/callback", "/reset-password"]) {
    assert.equal(usernameGate({ ...signedIn, pathname }), "pass", pathname);
  }
  assert.equal(pathIsOpen("/termsandmore"), false);
});

test("existing users with a username, and signed-out visitors, pass", () => {
  assert.equal(usernameGate({ ...signedIn, username: "trail_jo" }), "pass");
  assert.equal(usernameGate({ ...signedIn, authStatus: "signedOut" }), "pass");
  assert.equal(usernameGate({ ...signedIn, authStatus: "loading" }), "pass");
});

test("while the profile loads, wait unless this browser has seen a username", () => {
  assert.equal(usernameGate({ ...signedIn, profileLoading: true }), "wait");
  assert.equal(usernameGate({ ...signedIn, profileLoading: true, knownToHaveUsername: true }), "pass");
  // A stale "has a username" hint can't win once the profile says otherwise.
  assert.equal(usernameGate({ ...signedIn, knownToHaveUsername: true }), "choose");
});

test("a profile that can't load doesn't lock the user out", () => {
  assert.equal(usernameGate({ ...signedIn, profileError: "We couldn't reach Trekly." }), "pass");
});
