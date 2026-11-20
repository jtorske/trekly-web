import test from "node:test";
import assert from "node:assert/strict";
import { ACCOUNT_BADGE_TEXT, accountBadge, labeledName } from "./accountLabels.ts";
import { postHref } from "./activity.ts";

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

test("an announcement links to its trail, or to @trekly without one", () => {
  const author = { username: "trekly", display_name: "Trekly", avatar_path: null, follow: null };
  const trail = { id: "abc" } as NonNullable<NonNullable<Parameters<typeof postHref>[0]["announcement"]>["trail"]>;
  assert.equal(postHref({ kind: "announcement", hike: null, author, announcement: { body: "Hi", trail, photo_url: null } }),
    "/trails?id=abc");
  assert.equal(postHref({ kind: "announcement", hike: null, author, announcement: { body: "Hi", trail: null, photo_url: null } }),
    "/u/trekly");
});
