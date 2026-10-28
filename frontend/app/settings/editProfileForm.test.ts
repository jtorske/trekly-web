import test from "node:test";
import assert from "node:assert/strict";
import { BIO_LIMIT, initialValues, isDirty, profileUpdate, validateProfile } from "./editProfileForm.ts";
import type { Profile } from "../../lib/accountApi.ts";

const profile: Profile = {
  id: "u1",
  email: "hiker@example.com",
  display_name: "Sam",
  username: "trail_sam",
  bio: "Loves ridgelines",
  home_region: null,
  avatar_path: null,
  member_since: null,
  counts: { saved_trails: 0, gear_items: 0 },
  visibility: "private",
};

test("initialValues turns nulls into empty strings", () => {
  assert.deepEqual(initialValues(profile), { display_name: "Sam", username: "trail_sam", bio: "Loves ridgelines", home_region: "" });
});

test("isDirty tracks text edits (the photo saves on its own)", () => {
  const initial = initialValues(profile);
  assert.equal(isDirty({ ...initial }, initial), false);
  assert.equal(isDirty({ ...initial, bio: "Loves valleys" }, initial), true);
  assert.equal(isDirty({ ...initial, home_region: "PNW" }, initial), true);
});

test("validateProfile checks username format and bio length", () => {
  const ok = initialValues(profile);
  assert.deepEqual(validateProfile(ok), {});
  assert.deepEqual(validateProfile({ ...ok, username: "Trail_Sam" }), {});
  assert.ok(validateProfile({ ...ok, username: "ab" }).username);
  assert.ok(validateProfile({ ...ok, username: "no spaces" }).username);
  // Required: a username can change but not be removed.
  assert.equal(validateProfile({ ...ok, username: "  " }).username, "Choose a username.");
  assert.ok(validateProfile({ ...ok, bio: "x".repeat(BIO_LIMIT + 1) }).bio);
  assert.deepEqual(validateProfile({ ...ok, bio: "x".repeat(BIO_LIMIT) }), {});
});

test("profileUpdate trims, lowercases the username and clears blanks", () => {
  assert.deepEqual(profileUpdate({ display_name: "  Sam ", username: " Trail_Sam ", bio: "   ", home_region: "PNW" }), {
    display_name: "Sam",
    username: "trail_sam",
    bio: null,
    home_region: "PNW",
  });
});
