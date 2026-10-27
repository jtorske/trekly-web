import test from "node:test";
import assert from "node:assert/strict";
import { ACCOUNT_LINKS, PROFILE_HREF, currentAccountHref } from "./accountMenu.ts";

test("currentAccountHref tells profile tabs apart", () => {
  assert.equal(currentAccountHref("/profile", ""), "/profile");
  assert.equal(currentAccountHref("/profile", "?tab=overview"), "/profile");
  assert.equal(currentAccountHref("/profile", "?tab=trips"), "/profile?tab=trips");
  assert.equal(currentAccountHref("/profile", "?tab=settings"), "/profile?tab=settings");
  assert.equal(currentAccountHref("/profile", "?tab=gear"), "/gear");
  assert.equal(currentAccountHref("/profile", "?tab=trails"), null);
});

test("currentAccountHref maps other account pages", () => {
  assert.equal(currentAccountHref("/plans", "?id=abc"), "/profile?tab=trips");
  assert.equal(currentAccountHref("/gear", ""), "/gear");
  assert.equal(currentAccountHref("/alerts", ""), "/alerts");
  assert.equal(currentAccountHref("/trail-list", ""), null);
  assert.equal(currentAccountHref("/gearbox", ""), null);
});

test("Settings sits between Alerts and Log out, and opens the profile's Settings tab", () => {
  const labels = ACCOUNT_LINKS.map((link) => link.label);
  assert.equal(labels.at(-1), "Settings");
  assert.equal(labels.at(-2), "Alerts");
  assert.equal(ACCOUNT_LINKS.at(-1)?.href, "/profile?tab=settings");
});

test("every current href is a menu link", () => {
  const hrefs = new Set([PROFILE_HREF, ...ACCOUNT_LINKS.map((link) => link.href)]);
  for (const [path, search] of [["/profile", ""], ["/profile", "?tab=trips"], ["/profile", "?tab=settings"], ["/gear", ""], ["/alerts", ""]]) {
    assert.ok(hrefs.has(currentAccountHref(path, search) ?? ""), `${path}${search}`);
  }
});
