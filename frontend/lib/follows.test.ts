import { test } from "node:test";
import assert from "node:assert/strict";
import { countLabel, followButton, followToast } from "./follows.ts";

test("the follow button says what it'll do", () => {
  assert.deepEqual(followButton("none", false), { label: "Follow", next: "follow" });
  assert.deepEqual(followButton("none", true), { label: "Request to follow", next: "follow" });
  assert.deepEqual(followButton("requested", true), { label: "Requested", next: "unfollow" });
  assert.deepEqual(followButton("following", true), { label: "Following", next: "unfollow" });
});

test("counts read naturally", () => {
  assert.equal(countLabel(0, "followers"), "0 followers");
  assert.equal(countLabel(1, "followers"), "1 follower");
  assert.equal(countLabel(1204, "following"), "1,204 following");
});

test("toasts after a follow change", () => {
  assert.equal(followToast("none", "following", "Ana"), "You're following Ana.");
  assert.match(followToast("none", "requested", "Ana") ?? "", /once they approve/);
  assert.equal(followToast("requested", "none", "Ana"), "Request cancelled.");
  assert.equal(followToast("following", "none", "Ana"), "You unfollowed Ana.");
  assert.equal(followToast("none", "none", "Ana"), null);
});
