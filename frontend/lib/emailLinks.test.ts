import test from "node:test";
import assert from "node:assert/strict";
import { CONFIRM_TYPES, EMAIL_SETTINGS_PATH, confirmDestination, confirmProblem, parseConfirmLink } from "./emailLinks.ts";

test("parseConfirmLink reads token_hash and type", () => {
  assert.deepEqual(parseConfirmLink("?token_hash=pkce_abc123&type=signup"), { tokenHash: "pkce_abc123", type: "signup" });
  assert.deepEqual(parseConfirmLink("token_hash=abc&type=email_change"), { tokenHash: "abc", type: "email_change" });
});

test("parseConfirmLink rejects cut-short or unknown links", () => {
  for (const search of ["", "?type=signup", "?token_hash=abc", "?token_hash=%20&type=signup", "?token_hash=abc&type=sms", "?token_hash=abc&type=SIGNUP"]) {
    assert.equal(parseConfirmLink(search), null, search);
  }
});

test("each link type lands somewhere sensible", () => {
  assert.equal(confirmDestination("signup"), "/welcome");
  assert.equal(confirmDestination("recovery"), "/reset-password");
  assert.equal(confirmDestination("invite"), "/reset-password");
  assert.equal(confirmDestination("email_change"), EMAIL_SETTINGS_PATH);
  assert.equal(confirmDestination("magiclink"), "/profile");
  for (const type of CONFIRM_TYPES) assert.match(confirmDestination(type), /^\/[a-z]/);
});

test("problems offer the right way forward", () => {
  assert.equal(confirmProblem(null, false).title, "This link is incomplete");
  assert.equal(confirmProblem("recovery", false).action.href, "/forgot-password");
  assert.equal(confirmProblem("signup", false).action.href, "/login");
  assert.equal(confirmProblem("signup", true).action.href, "/welcome");
  assert.equal(confirmProblem("email_change", true).action.href, EMAIL_SETTINGS_PATH);
  assert.match(confirmProblem("email_change", false).action.href, /^\/login\?next=/);
  assert.match(confirmProblem("magiclink", false).subtitle, /expired or was already used/);
});
