import test from "node:test";
import assert from "node:assert/strict";
import {
  activityBlocker,
  appendPage,
  canShareHikes,
  earnedPhrases,
  highFiversLine,
  joinWords,
  latestEarned,
  postAction,
  postHref,
  shortAgo,
  type ActivityEarned,
  type ActivityPost,
} from "./activity.ts";
import type { Milestone } from "./milestones.ts";
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

test("lists read naturally", () => {
  assert.equal(joinWords([]), "");
  assert.equal(joinWords(["A"]), "A");
  assert.equal(joinWords(["A", "B"]), "A and B");
  assert.equal(joinWords(["A", "B", "C"]), "A, B and C");
});

test("what a hike earned, folded into its post", () => {
  const badge = (title: string): ActivityEarned => ({
    kind: "milestone",
    milestone: { id: title, category: "x", title, tier: "bronze", icon: "x" },
    rank: null,
  });
  assert.deepEqual(earnedPhrases([]), []);
  assert.deepEqual(earnedPhrases([badge("Divide crosser"), badge("Trail regular")]), [
    "earned Divide crosser and Trail regular",
  ]);
  assert.deepEqual(
    earnedPhrases([badge("First steps"), { kind: "rank", milestone: null, rank: { level: 2, title: "Day Tripper" } }]),
    ["earned First steps", "reached Day Tripper"],
  );
});

test("who high-fived", () => {
  const name = (a: { username: string }) => `@${a.username}`;
  const hiker = (username: string) => ({ username, display_name: null, avatar_path: null });
  assert.equal(highFiversLine({ hikers: [], others: 0 }, name), "No high fives yet");
  assert.equal(highFiversLine({ hikers: [hiker("ben")], others: 0 }, name), "@ben high-fived this");
  assert.equal(highFiversLine({ hikers: [hiker("ben")], others: 1 }, name), "@ben and 1 other high-fived this");
  assert.equal(highFiversLine({ hikers: [hiker("ben"), hiker("ana")], others: 3 }, name), "@ben, @ana and 3 others high-fived this");
  assert.equal(highFiversLine({ hikers: [], others: 2 }, name), "2 others high-fived this");
});

test("the most recently earned milestone", () => {
  const m = (id: string, earned_on: string | null, earned = true) => ({ id, earned, earned_on }) as Milestone;
  assert.equal(latestEarned([]), null);
  assert.equal(latestEarned([m("a", null), m("b", "2026-11-01", false)]), null);
  assert.equal(latestEarned([m("a", "2026-10-01"), m("b", "2026-11-02"), m("c", "2026-11-02")])?.id, "b");
});
