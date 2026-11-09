import test from "node:test";
import assert from "node:assert/strict";
import { activityBlocker, appendPage, canShareHikes, postAction, postHref, shortAgo, type ActivityPost } from "./activity.ts";
import type { TrailListItem } from "./trailsApi.ts";

const settings = { username: "alice", is_private: false, show_journal: true, share_activity: true };

test("sharing needs a username, a public profile and a public journal", () => {
  assert.equal(activityBlocker(settings), null);
  assert.match(activityBlocker({ ...settings, username: null })!, /username/);
  assert.match(activityBlocker({ ...settings, is_private: true })!, /private/);
  assert.match(activityBlocker({ ...settings, show_journal: false })!, /Trail Journal/);
});

test("the hike dialog's checkbox follows the setting", () => {
  assert.equal(canShareHikes(settings), true);
  assert.equal(canShareHikes({ ...settings, share_activity: false }), false);
  assert.equal(canShareHikes({ ...settings, is_private: true }), false);
});

const author = { username: "al ice", display_name: "Alice", avatar_path: null };
const trail = { id: "t/1" } as TrailListItem;

test("hike posts open the trail; badge posts open the profile", () => {
  const hike = { kind: "hike" as const, author, hike: { trail, hiked_on: null, note: null, photo_path: null, verified: false } };
  assert.equal(postHref(hike), "/trails?id=t%2F1");
  assert.equal(postHref({ kind: "rank", author, hike: null }), "/u/al%20ice");
});

test("compact post lines", () => {
  const milestone = { id: "parks", category: "exploration", title: "Park hopper", tier: "bronze" as const, icon: "x" };
  assert.equal(postAction({ kind: "milestone", milestone, rank: null }), "earned Park hopper");
  assert.equal(postAction({ kind: "rank", milestone: null, rank: { level: 4, title: "Ridge Walker" } }), "reached Ridge Walker");
});

test("short relative times", () => {
  const now = new Date("2026-11-09T12:00:00Z");
  assert.equal(shortAgo("2026-11-09T11:59:40Z", now), "now");
  assert.equal(shortAgo("2026-11-09T11:15:00Z", now), "45m");
  assert.equal(shortAgo("2026-11-09T07:00:00Z", now), "5h");
  assert.equal(shortAgo("2026-11-06T12:00:00Z", now), "3d");
  assert.equal(shortAgo("2026-10-01T12:00:00Z", now), "Oct 1");
  assert.equal(shortAgo("2025-10-01T12:00:00Z", now), "Oct 1, 2025");
});

test("pages append without repeating a post", () => {
  const post = (id: string) => ({ id }) as ActivityPost;
  assert.deepEqual(appendPage([post("a"), post("b")], [post("b"), post("c")]).map((p) => p.id), ["a", "b", "c"]);
});
