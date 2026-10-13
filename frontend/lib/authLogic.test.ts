import test from "node:test";
import assert from "node:assert/strict";
import {
  authRedirectError,
  emailLooksValid,
  friendlyAuthError,
  passwordChecks,
  passwordIsValid,
  safeNextPath,
} from "./authLogic.ts";

test("safeNextPath keeps same-site paths", () => {
  assert.equal(safeNextPath("/gear"), "/gear");
  assert.equal(safeNextPath("/trails?id=abc&save=1"), "/trails?id=abc&save=1");
  assert.equal(safeNextPath(encodeURIComponent("/trails?id=abc")), "/trails?id=abc");
});

test("safeNextPath blocks open redirects and loops", () => {
  for (const bad of [
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "javascript:alert(1)",
    "%2F%2Fevil.example",
    "/login",
    "/signup?next=/gear",
    "/auth/callback",
    "/x\n",
    "%E0%A4%A",
    "",
    null,
  ]) {
    assert.equal(safeNextPath(bad as string | null), "/profile", String(bad));
  }
  assert.equal(safeNextPath(null, "/gear"), "/gear");
});

test("password requirements", () => {
  assert.equal(passwordIsValid("short1"), false);
  assert.equal(passwordIsValid("longenough"), false);
  assert.equal(passwordIsValid("12345678"), false);
  assert.equal(passwordIsValid("trail-mix"), true);
  assert.equal(passwordIsValid("hiking2026"), true);
  assert.deepEqual(
    passwordChecks("abc").map((c) => c.met),
    [false, true, false],
  );
});

test("email validation", () => {
  assert.equal(emailLooksValid(" hiker@example.com "), true);
  assert.equal(emailLooksValid("hiker@example"), false);
  assert.equal(emailLooksValid("hiker example.com"), false);
});

test("friendly errors don't reveal whether an account exists", () => {
  const invalid = friendlyAuthError(Object.assign(new Error("Invalid login credentials"), { code: "invalid_credentials" }));
  assert.match(invalid, /don't match/);
  assert.doesNotMatch(invalid, /no account|not found|exists/i);
  assert.match(friendlyAuthError(new Error("Email not confirmed")), /Confirm your email/);
  assert.match(friendlyAuthError(new TypeError("Failed to fetch")), /couldn't reach/);
  assert.match(friendlyAuthError(new Error("email rate limit exceeded")), /Too many attempts/);
});

test("auth redirect errors are read from query or hash", () => {
  assert.match(
    authRedirectError("", "#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired") ?? "",
    /invalid or has expired/,
  );
  assert.match(authRedirectError("?error_description=Email%20link%20is%20invalid%20or%20has%20expired", "") ?? "", /expired/);
  assert.equal(authRedirectError("?code=abc", ""), null);
});
