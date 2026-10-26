import test from "node:test";
import assert from "node:assert/strict";
import { readImageType, sniffImageType } from "./imageType.ts";

const JPEG = [0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01];
const PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d];
const WEBP = [...Buffer.from("RIFF"), 0x24, 0x00, 0x00, 0x00, ...Buffer.from("WEBPVP8 ")];

test("recognises JPEG, PNG and WebP from their first bytes", () => {
  assert.equal(sniffImageType(new Uint8Array(JPEG)), "image/jpeg");
  assert.equal(sniffImageType(new Uint8Array(PNG)), "image/png");
  assert.equal(sniffImageType(new Uint8Array(WEBP)), "image/webp");
});

test("rejects text, other formats, other RIFF files and empty files", () => {
  assert.equal(sniffImageType(new TextEncoder().encode("hello, this is not a photo")), null);
  assert.equal(sniffImageType(new TextEncoder().encode("GIF89a......")), null);
  assert.equal(sniffImageType(new TextEncoder().encode("<svg xmlns=")), null);
  assert.equal(sniffImageType(new Uint8Array([...Buffer.from("RIFF"), 0, 0, 0, 0, ...Buffer.from("WAVE")])), null);
  assert.equal(sniffImageType(new Uint8Array([0xff, 0xd8])), null);
  assert.equal(sniffImageType(new Uint8Array()), null);
});

test("reads the type from a file's contents, not its declared type", async () => {
  const renamedText = new Blob(["just some text"], { type: "image/jpeg" });
  assert.equal(await readImageType(renamedText), null);
  const pngNamedJpeg = new Blob([new Uint8Array(PNG)], { type: "image/jpeg" });
  assert.equal(await readImageType(pngNamedJpeg), "image/png");
});
