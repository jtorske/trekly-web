import test from "node:test";
import assert from "node:assert/strict";
import { statSync } from "node:fs";
import { LANDING_PHOTOS, WINTER_LANDING_PHOTOS, landingPhotosFor, pickLandingPhoto, type LandingPhoto } from "./landingPhotos.ts";

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

test("winter photos are credited with author and licence, local, and under 400 KB", () => {
  assert.ok(WINTER_LANDING_PHOTOS.length > 1);
  const sources = WINTER_LANDING_PHOTOS.map((photo) => photo.src);
  assert.equal(new Set(sources).size, sources.length);
  for (const photo of WINTER_LANDING_PHOTOS) {
    assert.match(photo.src, /^\/images\/[^/]+\.webp$/);
    assert.ok(photo.credit, photo.src);
    assert.match(photo.credit.text, /CC (BY|BY-SA|0)( \d\.\d)?/, photo.src);
    assert.match(photo.credit.href ?? "", /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/, photo.src);
    const size = statSync(new URL(`../public${photo.src}`, import.meta.url)).size;
    assert.ok(size <= 400 * 1024, `${photo.src} is ${size} bytes`);
  }
});

test("the hero pool follows the season", () => {
  assert.equal(landingPhotosFor("winter"), WINTER_LANDING_PHOTOS);
  assert.equal(landingPhotosFor("summer"), LANDING_PHOTOS);
  assert.equal(landingPhotosFor(null), LANDING_PHOTOS);
});
