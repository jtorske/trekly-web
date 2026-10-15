import test from "node:test";
import assert from "node:assert/strict";
import { AVATAR_MAX_INPUT_BYTES, MAX_ZOOM, clampOffset, clampZoom, cropRect, validateAvatarFile } from "./avatarImage.ts";

const MB = 1024 * 1024;

test("accepts JPEG, PNG and WebP up to 5 MB", () => {
  for (const type of ["image/jpeg", "image/png", "image/webp"]) {
    assert.equal(validateAvatarFile({ type, size: 2 * MB }), null);
  }
  assert.equal(validateAvatarFile({ type: "image/jpeg", size: AVATAR_MAX_INPUT_BYTES }), null);
});

test("rejects other file types with a clear message", () => {
  for (const type of ["image/gif", "image/heic", "image/svg+xml", "application/pdf", ""]) {
    assert.match(validateAvatarFile({ type, size: MB }) ?? "", /JPEG, PNG or WebP/);
  }
});

test("rejects photos over 5 MB and says how big they are", () => {
  assert.match(validateAvatarFile({ type: "image/png", size: AVATAR_MAX_INPUT_BYTES + 1 }) ?? "", /5\.0 MB.*5 MB or smaller/);
  assert.match(validateAvatarFile({ type: "image/jpeg", size: 12.3 * MB }) ?? "", /12\.3 MB/);
  assert.ok(validateAvatarFile({ type: "image/jpeg", size: 0 }));
});

test("at zoom 1 the crop is the centred largest square", () => {
  assert.deepEqual(cropRect({ width: 4000, height: 3000 }, 240, 1, { x: 0, y: 0 }), { sx: 500, sy: 0, size: 3000 });
  assert.deepEqual(cropRect({ width: 1000, height: 2000 }, 240, 1, { x: 0, y: 0 }), { sx: 0, sy: 500, size: 1000 });
});

test("zooming in crops a smaller square around the centre", () => {
  assert.deepEqual(cropRect({ width: 1000, height: 1000 }, 200, 2, { x: 0, y: 0 }), { sx: 250, sy: 250, size: 500 });
});

test("panning can't move the image off the frame", () => {
  const image = { width: 4000, height: 3000 };
  // Landscape at zoom 1: only horizontal movement, up to the image edge.
  assert.deepEqual(clampOffset(image, 240, 1, { x: 999, y: 999 }), { x: 40, y: 0 });
  assert.deepEqual(cropRect(image, 240, 1, { x: 999, y: 0 }), { sx: 0, sy: 0, size: 3000 });
  assert.deepEqual(cropRect(image, 240, 1, { x: -999, y: 0 }), { sx: 1000, sy: 0, size: 3000 });
});

test("the crop always stays inside the source image", () => {
  const image = { width: 1200, height: 800 };
  for (const zoom of [1, 1.5, 2.25, MAX_ZOOM]) {
    for (const offset of [{ x: -500, y: -500 }, { x: 500, y: 500 }, { x: 13, y: -7 }]) {
      const { sx, sy, size } = cropRect(image, 240, zoom, offset);
      assert.ok(sx >= -1e-9 && sy >= -1e-9, `origin inside at zoom ${zoom}`);
      assert.ok(sx + size <= image.width + 1e-9 && sy + size <= image.height + 1e-9, `far edge inside at zoom ${zoom}`);
    }
  }
});

test("zoom stays between 1x and the maximum", () => {
  assert.equal(clampZoom(0.2), 1);
  assert.equal(clampZoom(2), 2);
  assert.equal(clampZoom(99), MAX_ZOOM);
});
