import test from "node:test";
import assert from "node:assert/strict";
import { backLink, returnablePath } from "./returnTo.ts";

const ORIGIN = "https://trekly.example";

test("no history goes to /profile", () => {
  assert.deepEqual(backLink(null, null, ORIGIN), { href: "/profile", label: "Back to profile" });
  assert.deepEqual(backLink(null, "", ORIGIN), { href: "/profile", label: "Back to profile" });
});

test("a public profile the user came from is where it goes back to", () => {
  assert.deepEqual(backLink("/u/ana_hikes", null, ORIGIN), { href: "/u/ana_hikes", label: "Back to profile" });
  assert.deepEqual(backLink("/profile?tab=activity", null, ORIGIN), {
    href: "/profile?tab=activity",
    label: "Back to profile",
  });
});

test("another page of ours goes back there, labelled plainly", () => {
  assert.deepEqual(backLink("/trails/lake-agnes", null, ORIGIN), { href: "/trails/lake-agnes", label: "Back" });
});

test("the remembered page wins over the referrer; the referrer fills in on a fresh load", () => {
  assert.equal(backLink("/activity", `${ORIGIN}/u/ben`, ORIGIN).href, "/activity");
  assert.equal(backLink(null, `${ORIGIN}/u/ben`, ORIGIN).href, "/u/ben");
});

test("other sites, Settings itself and sign-in pages are never targets", () => {
  assert.equal(returnablePath("https://evil.example/u/ana", ORIGIN), null);
  assert.equal(returnablePath("//evil.example/u/ana", ORIGIN), null);
  assert.equal(returnablePath("/settings/privacy", ORIGIN), null);
  assert.equal(returnablePath("/settings", ORIGIN), null);
  assert.equal(returnablePath("/login?next=/settings", ORIGIN), null);
  assert.equal(returnablePath("/auth/confirm", ORIGIN), null);
  assert.equal(backLink(`${ORIGIN}/settings/units`, "https://evil.example/", ORIGIN).href, "/profile");
});

test("a path that only starts like a skipped one is fine", () => {
  assert.equal(returnablePath("/settingsfoo", ORIGIN), "/settingsfoo");
});
