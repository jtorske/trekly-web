import test from "node:test";
import assert from "node:assert/strict";
import { isIndexable, trailHref } from "./site.ts";

test("trail links use the slug", () => {
  assert.equal(trailHref({ id: "1", slug: "lake-agnes-tea-house" }), "/trails/lake-agnes-tea-house");
  assert.equal(trailHref({ id: "1", slug: "skyline-trail" }, "start=2026-07-01"), "/trails/skyline-trail?start=2026-07-01");
  // Without a slug, the id form (the server 301s it to the slug).
  assert.equal(trailHref({ id: "a/b" }), "/trails?id=a%2Fb");
  assert.equal(trailHref({ id: "a" }, "save=a"), "/trails?id=a&save=a");
});

test("only Vercel production is indexable", () => {
  assert.equal(isIndexable({ VERCEL_ENV: "production" }), true);
  assert.equal(isIndexable({ VERCEL_ENV: "preview" }), false);
  assert.equal(isIndexable({}), false);
});
