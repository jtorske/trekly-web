import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_USERS_QUERY,
  confirmationFor,
  formatDate,
  timeAgo,
  nextSort,
  pageCount,
  parseUsersQuery,
  providerLabel,
  usersQueryString,
  whoLabel,
} from "./adminView.ts";

test("the users table reads its state from the URL and ignores junk", () => {
  assert.deepEqual(parseUsersQuery(new URLSearchParams("")), DEFAULT_USERS_QUERY);
  assert.deepEqual(parseUsersQuery(new URLSearchParams("q=alice&sort=hikes&dir=asc&filter=banned&page=3")), {
    q: "alice", sort: "hikes", dir: "asc", filter: "banned", page: 3,
  });
  assert.deepEqual(parseUsersQuery(new URLSearchParams("sort=password&dir=up&filter=admins&page=-2")), DEFAULT_USERS_QUERY);
  assert.equal(parseUsersQuery(new URLSearchParams(`q=${"x".repeat(300)}`)).q.length, 100);
});

test("the URL leaves out defaults and round-trips", () => {
  assert.equal(usersQueryString(DEFAULT_USERS_QUERY), "");
  const query = { q: " bob ", sort: "email", dir: "asc", filter: "hidden", page: 2 } as const;
  const text = usersQueryString(query);
  assert.equal(text, "?q=bob&sort=email&dir=asc&filter=hidden&page=2");
  assert.deepEqual(parseUsersQuery(new URLSearchParams(text)), { ...query, q: "bob" });
});

test("sorting flips the current column and starts others in their natural direction", () => {
  const page3 = { ...DEFAULT_USERS_QUERY, page: 3 };
  assert.deepEqual(nextSort(page3, "joined"), { ...DEFAULT_USERS_QUERY, dir: "asc", page: 1 });
  assert.equal(nextSort(page3, "email").dir, "asc");
  assert.equal(nextSort(page3, "hikes").dir, "desc");
  assert.equal(nextSort(page3, "hikes").page, 1);
});

test("page counts never go below one", () => {
  assert.equal(pageCount(0, 25), 1);
  assert.equal(pageCount(25, 25), 1);
  assert.equal(pageCount(26, 25), 2);
});

test("labels", () => {
  assert.equal(providerLabel("google"), "Google");
  assert.equal(providerLabel("discord"), "Discord");
  assert.equal(whoLabel({ id: "abc", username: "alice", display_name: "Alice" }), "@alice");
  assert.equal(whoLabel({ id: "abc", username: null, display_name: null, email: "a@b.c" }), "a@b.c");
  assert.equal(whoLabel({ id: "0123456789", username: null }), "user 01234567");
});

test("every account action has a confirmation, and risky ones ask for a reason", () => {
  for (const action of ["hide", "unhide", "clear-username", "ban", "unban", "password-reset"] as const) {
    const c = confirmationFor(action, "@alice", "alice@example.com");
    assert.ok(c.title.includes("@alice") && c.body && c.confirm, action);
  }
  assert.equal(confirmationFor("ban", "@a", null).danger, true);
  assert.equal(confirmationFor("ban", "@a", null).reason, true);
  assert.equal(confirmationFor("unban", "@a", null).reason, false);
  assert.match(confirmationFor("password-reset", "@a", "a@b.c").body, /a@b\.c/);
});

test("dates", () => {
  const now = Date.parse("2026-11-02T12:00:00Z");
  assert.equal(timeAgo(null, now), "—");
  assert.equal(timeAgo("2026-11-02T11:59:40Z", now), "just now");
  assert.equal(timeAgo("2026-11-02T11:48:00Z", now), "12 min ago");
  assert.equal(timeAgo("2026-11-02T09:00:00Z", now), "3 h ago");
  assert.equal(timeAgo("2026-11-01T11:00:00Z", now), "1 day ago");
  assert.equal(formatDate("2026-08-14"), "Aug 14, 2026");
  assert.equal(formatDate("nonsense"), "—");
});
