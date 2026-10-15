import test from "node:test";
import assert from "node:assert/strict";
import { BIO_LIMIT, closeAction, initialValues, isDirty, profileUpdate, staleAvatar, validateProfile } from "./editProfileForm.ts";
import type { Profile } from "../../lib/accountApi.ts";

const profile: Profile = {
  id: "u1",
  email: "hiker@example.com",
  display_name: "Sam",
  username: null,
  bio: "Loves ridgelines",
  home_region: null,
  avatar_path: null,
  member_since: null,
  counts: { saved_trails: 0, gear_items: 0 },
  visibility: "private",
};

test("initialValues turns nulls into empty strings", () => {
  assert.deepEqual(initialValues(profile), { display_name: "Sam", username: "", bio: "Loves ridgelines", home_region: "" });
});

test("isDirty tracks text edits and avatar changes", () => {
  const initial = initialValues(profile);
  const noAvatar = { file: null, remove: false };
  assert.equal(isDirty({ ...initial }, initial, noAvatar), false);
  assert.equal(isDirty({ ...initial, bio: "Loves valleys" }, initial, noAvatar), true);
  assert.equal(isDirty(initial, initial, { file: {}, remove: false }), true);
  assert.equal(isDirty(initial, initial, { file: null, remove: true }), true);
});

test("validateProfile checks username format and bio length", () => {
  const ok = initialValues(profile);
  assert.deepEqual(validateProfile(ok), {});
  assert.deepEqual(validateProfile({ ...ok, username: "Trail_Sam" }), {});
  assert.ok(validateProfile({ ...ok, username: "ab" }).username);
  assert.ok(validateProfile({ ...ok, username: "no spaces" }).username);
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

test("a pending photo change counts as unsaved", () => {
  const initial = initialValues(profile);
  const croppedPhoto = { blob: {}, extension: "webp" };
  assert.equal(isDirty(initial, initial, { file: croppedPhoto, remove: false }), true);
  assert.equal(isDirty(initial, initial, { file: null, remove: true }), true);
  assert.equal(closeAction({ dirty: isDirty(initial, initial, { file: croppedPhoto, remove: false }), confirming: false }), "confirm");
});

test("staleAvatar deletes the old file only when it was replaced or removed", () => {
  assert.equal(staleAvatar("u1/old.webp", "u1/new.webp"), "u1/old.webp");
  assert.equal(staleAvatar("u1/old.webp", null), "u1/old.webp");
  assert.equal(staleAvatar("u1/old.webp", "u1/old.webp"), null);
  assert.equal(staleAvatar(null, "u1/new.webp"), null);
});

test("closeAction asks before discarding unsaved changes", () => {
  assert.equal(closeAction({ dirty: false, confirming: false }), "close");
  assert.equal(closeAction({ dirty: true, confirming: false }), "confirm");
  // A second close request (e.g. Escape) while asking backs out of the prompt.
  assert.equal(closeAction({ dirty: true, confirming: true }), "keep-editing");
});
