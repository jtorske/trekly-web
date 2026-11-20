import { test } from "node:test";
import assert from "node:assert/strict";
import { actionText, badgeText, notificationHref, whoText, type NotificationActor } from "./notifications.ts";

const ana: NotificationActor = { username: "ana", display_name: "Ana", avatar_path: null };
const ben: NotificationActor = { username: "ben", display_name: null, avatar_path: null };
const hike = { id: "p1", kind: "hike" as const, title: "Bald Hills", trail_id: "t1" };

test("names read like a sentence", () => {
  assert.equal(whoText([ana], 1), "Ana");
  assert.equal(whoText([ana, ben], 2), "Ana and @ben");
  assert.equal(whoText([ana, ben], 4), "Ana and 3 others");
  assert.equal(whoText([], 0), "Someone");
});

test("what happened", () => {
  assert.equal(actionText({ kind: "high_five", post: hike }), "high-fived your hike on Bald Hills");
  assert.equal(
    actionText({ kind: "comment", post: { id: "p2", kind: "milestone", title: "Double header", trail_id: null } }),
    "commented on your Double header badge",
  );
  assert.equal(actionText({ kind: "follow_request", post: null }), "asked to follow you");
});

test("where an item goes", () => {
  assert.equal(notificationHref({ kind: "new_follower", post: null, actors: [ana], actor_count: 1 }), "/u/ana");
  assert.equal(notificationHref({ kind: "new_follower", post: null, actors: [ana, ben], actor_count: 2 }), "/profile");
  assert.equal(notificationHref({ kind: "high_five", post: hike, actors: [ana], actor_count: 1 }), "/trails?id=t1");
});

test("badge", () => {
  assert.equal(badgeText(0), null);
  assert.equal(badgeText(3), "3");
  assert.equal(badgeText(12), "9+");
});

test("comment notifications say what happened and open the post's own page", () => {
  const post = { id: "p9", kind: "hike" as const, title: "Lake Agnes", trail_id: "t1" };
  assert.equal(actionText({ kind: "comment", post }), "commented on your hike on Lake Agnes");
  assert.equal(actionText({ kind: "comment_reply", post }), "replied to your comment");
  assert.equal(actionText({ kind: "mention", post }), "mentioned you in a comment");
  for (const kind of ["comment", "comment_reply", "mention"] as const) {
    assert.equal(notificationHref({ kind, post, actors: [], actor_count: 1 }), "/activity/p9");
  }
});
