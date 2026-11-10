import test from "node:test";
import assert from "node:assert/strict";
import { ACCOUNT_BADGE_TEXT, accountBadge, labeledName } from "./accountLabels.ts";
import { PICK_EVERY, postHref, withPicks, type FeedPick, type FeedPicks } from "./activity.ts";

test("official and demo accounts always get their badge words", () => {
  assert.equal(accountBadge("official"), "Trekly team");
  assert.equal(accountBadge("demo"), "Demo account");
  assert.equal(accountBadge(null), null);
  assert.equal(accountBadge(undefined), null);
  assert.deepEqual(Object.keys(ACCOUNT_BADGE_TEXT).sort(), ["demo", "official"]);
});

test("names in sentences carry the label too", () => {
  assert.equal(labeledName("Maya", "demo"), "Maya (Demo account)");
  assert.equal(labeledName("Trekly", "official"), "Trekly (Trekly team)");
  assert.equal(labeledName("Ana", null), "Ana");
});

const pick = (n: number): FeedPick => ({
  kind: "trending",
  title: `Pick ${n}`,
  text: "",
  trail: { id: `t${n}` } as FeedPick["trail"],
});
const picks = (sparse: boolean, count = 3): FeedPicks => ({ sparse, picks: Array.from({ length: count }, (_, n) => pick(n)) });
const shape = (items: ({ post: number } | { pick: FeedPick })[]) =>
  items.map((item) => ("pick" in item ? `p:${item.pick.title}` : String(item.post))).join(" ");

test("picks go in after every few posts while the feed is quiet", () => {
  const posts = Array.from({ length: PICK_EVERY * 2 + 1 }, (_, n) => n);
  assert.equal(shape(withPicks(posts, picks(true))), "0 1 2 3 p:Pick 0 4 5 6 7 p:Pick 1 8 p:Pick 2");
});

test("a short quiet feed still ends with a pick", () => {
  assert.equal(shape(withPicks([0, 1], picks(true))), "0 1 p:Pick 0");
});

test("no picks once the feed isn't quiet, or before they load", () => {
  const posts = [0, 1, 2, 3, 4];
  assert.equal(shape(withPicks(posts, picks(false))), "0 1 2 3 4");
  assert.equal(shape(withPicks(posts, null)), "0 1 2 3 4");
});

test("an announcement links to its trail, or to @trekly without one", () => {
  const author = { username: "trekly", display_name: "Trekly", avatar_path: null, follow: null };
  const trail = { id: "abc" } as NonNullable<NonNullable<Parameters<typeof postHref>[0]["announcement"]>["trail"]>;
  assert.equal(postHref({ kind: "announcement", hike: null, author, announcement: { body: "Hi", trail, photo_url: null } }),
    "/trails?id=abc");
  assert.equal(postHref({ kind: "announcement", hike: null, author, announcement: { body: "Hi", trail: null, photo_url: null } }),
    "/u/trekly");
});
