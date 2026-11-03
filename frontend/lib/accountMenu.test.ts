import test from "node:test";
import assert from "node:assert/strict";
import { ACCOUNT_LINKS, ADMIN_LINK, PROFILE_HREF, accountLinks, currentAccountHref } from "./accountMenu.ts";

test("currentAccountHref tells profile tabs apart", () => {
  assert.equal(currentAccountHref("/profile", ""), "/profile");
  assert.equal(currentAccountHref("/profile", "?tab=overview"), "/profile");
  assert.equal(currentAccountHref("/profile", "?tab=trips"), "/profile?tab=trips");
  assert.equal(currentAccountHref("/profile", "?tab=settings"), "/settings");
  assert.equal(currentAccountHref("/profile", "?tab=gear"), "/gear");
  assert.equal(currentAccountHref("/profile", "?tab=trails"), null);
});

test("currentAccountHref maps other account pages", () => {
  assert.equal(currentAccountHref("/plans", "?id=abc"), "/profile?tab=trips");
  assert.equal(currentAccountHref("/gear", ""), "/gear");
  assert.equal(currentAccountHref("/alerts", ""), "/alerts");
  assert.equal(currentAccountHref("/settings", ""), "/settings");
  assert.equal(currentAccountHref("/settings/privacy", ""), "/settings");
  assert.equal(currentAccountHref("/trail-list", ""), null);
  assert.equal(currentAccountHref("/gearbox", ""), null);
});

test("Settings sits between Alerts and Log out, and opens the Settings page", () => {
  const labels = ACCOUNT_LINKS.map((link) => link.label);
  assert.equal(labels.at(-1), "Settings");
  assert.equal(labels.at(-2), "Alerts");
  assert.equal(ACCOUNT_LINKS.at(-1)?.href, "/settings");
});

test("every current href is a menu link", () => {
  const hrefs = new Set([PROFILE_HREF, ...ACCOUNT_LINKS.map((link) => link.href)]);
  for (const [path, search] of [["/profile", ""], ["/profile", "?tab=trips"], ["/settings/units", ""], ["/gear", ""], ["/alerts", ""]]) {
    assert.ok(hrefs.has(currentAccountHref(path, search) ?? ""), `${path}${search}`);
  }
});

test("only admins get the Admin row, after Settings", () => {
  assert.deepEqual(accountLinks(false), ACCOUNT_LINKS);
  assert.ok(!accountLinks(false).some((link) => link.href === "/admin"));
  const admin = accountLinks(true);
  assert.deepEqual(admin.at(-1), ADMIN_LINK);
  assert.equal(admin.at(-2)?.href, "/settings");
  assert.equal(currentAccountHref("/admin", ""), "/admin");
  assert.equal(currentAccountHref("/admin/users/abc", ""), "/admin");
  assert.equal(currentAccountHref("/administrator", ""), null);
});
