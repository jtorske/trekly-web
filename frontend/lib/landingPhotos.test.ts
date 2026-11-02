import test from "node:test";
import assert from "node:assert/strict";
import { LANDING_PHOTOS, pickLandingPhoto, type LandingPhoto } from "./landingPhotos.ts";

const POOL: LandingPhoto[] = [{ src: "/a.jpg" }, { src: "/b.jpg" }, { src: "/c.jpg" }];

test("never repeats the last photo", () => {
  for (const last of POOL) {
    for (const r of [0, 0.34, 0.5, 0.67, 0.999999]) {
      assert.notEqual(pickLandingPhoto(POOL, last.src, () => r).src, last.src);
    }
  }
});

test("can pick every other photo", () => {
  const picked = new Set([0, 0.5, 0.99].map((r) => pickLandingPhoto(POOL, "/a.jpg", () => r).src));
  assert.deepEqual([...picked].sort(), ["/b.jpg", "/c.jpg"]);
});

test("a first visit or an unknown cookie draws from the whole pool", () => {
  assert.equal(pickLandingPhoto(POOL, undefined, () => 0).src, "/a.jpg");
  assert.equal(pickLandingPhoto(POOL, "/gone.jpg", () => 0.99).src, "/c.jpg");
});

test("a one-photo pool always shows that photo", () => {
  assert.equal(pickLandingPhoto([{ src: "/a.jpg" }], "/a.jpg", () => 0.5).src, "/a.jpg");
});

test("the configured pool has no duplicates and only local images", () => {
  const sources = LANDING_PHOTOS.map((photo) => photo.src);
  assert.ok(sources.length > 1);
  assert.equal(new Set(sources).size, sources.length);
  for (const src of sources) assert.match(src, /^\/images\/[^/]+\.(jpe?g|png|webp)$/i);
});
