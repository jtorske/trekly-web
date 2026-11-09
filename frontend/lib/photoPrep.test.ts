import test from "node:test";
import assert from "node:assert/strict";
import { isHeif, sniffPhotoType } from "./imageType.ts";
import {
  EMPTY_FILE,
  NOT_A_PHOTO,
  PHOTO_PICK_MAX_BYTES,
  PREPARE_FAILED,
  TOO_LARGE,
  orientationMatrix,
  orientedSize,
  photoProblemMessage,
  planRender,
  preparePhotoWith,
  readExifOrientation,
  type DecodedPhoto,
  type Matrix,
  type Orientation,
  type PhotoDeps,
  type RenderPlan,
} from "./photoPrep.ts";

const MB = 1024 * 1024;

// ------------------------------------------------------------ fixtures

/** A JPEG start: SOI, an Exif APP1 with one IFD0 entry (orientation), then SOF0. */
function jpegWithOrientation(orientation: number, order: "II" | "MM" = "MM"): Uint8Array {
  const little = order === "II";
  const tiff = new DataView(new ArrayBuffer(26));
  tiff.setUint8(0, order.charCodeAt(0));
  tiff.setUint8(1, order.charCodeAt(1));
  tiff.setUint16(2, 42, little);
  tiff.setUint32(4, 8, little); // IFD0 right after the header
  tiff.setUint16(8, 1, little); // one entry
  tiff.setUint16(10, 0x0112, little); // Orientation
  tiff.setUint16(12, 3, little); // SHORT
  tiff.setUint32(14, 1, little);
  tiff.setUint16(18, orientation, little);
  tiff.setUint32(22, 0, little); // no next IFD
  const exif = [...Buffer.from("Exif\0\0"), ...new Uint8Array(tiff.buffer)];
  const app1 = [0xff, 0xe1, (exif.length + 2) >> 8, (exif.length + 2) & 0xff, ...exif];
  // A JFIF APP0 first, as most cameras write, so the walker has to skip a segment.
  const app0 = [0xff, 0xe0, 0x00, 0x10, ...Buffer.from("JFIF\0"), 1, 1, 0, 0, 1, 0, 1, 0, 0];
  const sof = [0xff, 0xc0, 0x00, 0x11, 8, 0x0b, 0xb8, 0x0f, 0xa0, 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1];
  return new Uint8Array([0xff, 0xd8, ...app0, ...app1, ...sof, 0xff, 0xda]);
}

/** The first bytes of an iPhone HEIC: an ftyp box with brand "heic". */
const HEIC = new Uint8Array([0, 0, 0, 0x18, ...Buffer.from("ftypheic"), 0, 0, 0, 0, ...Buffer.from("mif1heic")]);
const AVIF = new Uint8Array([0, 0, 0, 0x1c, ...Buffer.from("ftypavif"), 0, 0, 0, 0, ...Buffer.from("avifmif1miaf")]);
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0x0d]);

/** A file of `size` bytes that starts with `head`. */
function fileOf(head: Uint8Array, size = 9 * MB, name = "IMG_1234.HEIC"): File {
  const bytes = new Uint8Array(size);
  bytes.set(head.slice(0, size));
  return new File([bytes], name);
}

/** Fake browser steps that record what preparePhoto asked for. */
function fakeDeps(decoded: { width: number; height: number; upright: boolean }, opts: { nativeFails?: boolean; heicFails?: boolean } = {}) {
  const calls: string[] = [];
  let plan: RenderPlan | null = null;
  let closed = 0;
  const photo = (): DecodedPhoto => ({ ...decoded, source: "pixels", close: () => void closed++ });
  const deps: PhotoDeps = {
    readHead: async (file) => {
      calls.push("readHead");
      return new Uint8Array(await file.slice(0, 128 * 1024).arrayBuffer());
    },
    decode: async () => {
      calls.push("decode");
      if (opts.nativeFails) throw new DOMException("The source image could not be decoded.", "InvalidStateError");
      return photo();
    },
    decodeHeic: async () => {
      calls.push("decodeHeic");
      if (opts.heicFails) throw new Error("HEIF processing error");
      return { ...photo(), upright: true };
    },
    render: async (_photo, next) => {
      calls.push("render");
      plan = next;
      return new Blob([new Uint8Array(200 * 1024)], { type: "image/jpeg" });
    },
  };
  return { deps, calls, plan: () => plan, closed: () => closed };
}

/** Where a matrix sends a point. */
const apply = ([a, b, c, d, e, f]: Matrix, x: number, y: number) => [a * x + c * y + e, b * x + d * y + f].map((n) => n + 0);

// ------------------------------------------------------------ type sniffing

test("recognises HEIC from its ftyp box, but not AVIF or other formats", () => {
  assert.equal(isHeif(HEIC), true);
  assert.equal(sniffPhotoType(HEIC), "image/heic");
  for (const brand of ["heix", "hevc", "mif1", "msf1"]) {
    const bytes = HEIC.slice();
    bytes.set(Buffer.from(brand), 8);
    assert.equal(sniffPhotoType(bytes), "image/heic", brand);
  }
  assert.equal(sniffPhotoType(AVIF), null);
  assert.equal(sniffPhotoType(PNG), "image/png");
  assert.equal(sniffPhotoType(new TextEncoder().encode("%PDF-1.7 not a photo")), null);
  assert.equal(sniffPhotoType(new Uint8Array()), null);
});

// ------------------------------------------------------------ orientation

test("reads the EXIF orientation of a phone photo, in either byte order", () => {
  for (const order of ["MM", "II"] as const) {
    for (let o = 1; o <= 8; o++) assert.equal(readExifOrientation(jpegWithOrientation(o, order)), o, `${order} ${o}`);
  }
});

test("photos without a usable orientation are treated as upright", () => {
  assert.equal(readExifOrientation(PNG), 1);
  assert.equal(readExifOrientation(jpegWithOrientation(0)), 1);
  assert.equal(readExifOrientation(jpegWithOrientation(9)), 1);
  // Cut off halfway through the Exif block.
  assert.equal(readExifOrientation(jpegWithOrientation(6).slice(0, 40)), 1);
  // A JPEG with no Exif at all.
  assert.equal(readExifOrientation(new Uint8Array([0xff, 0xd8, 0xff, 0xda, 0, 2])), 1);
});

test("quarter-turn orientations swap width and height", () => {
  assert.deepEqual(orientedSize(4032, 3024, 1), { width: 4032, height: 3024 });
  assert.deepEqual(orientedSize(4032, 3024, 3), { width: 4032, height: 3024 });
  for (const o of [5, 6, 7, 8] as const) assert.deepEqual(orientedSize(4032, 3024, o), { width: 3024, height: 4032 });
});

test("every orientation's transform maps the photo exactly onto the upright canvas", () => {
  const w = 40;
  const h = 30;
  for (let o = 1 as Orientation; o <= 8; o = (o + 1) as Orientation) {
    const out = orientedSize(w, h, o);
    const m = orientationMatrix(o, w, h);
    const corners = [apply(m, 0, 0), apply(m, w, 0), apply(m, 0, h), apply(m, w, h)].map((p) => p.join(","));
    assert.deepEqual(new Set(corners), new Set(["0,0", `${out.width},0`, `0,${out.height}`, `${out.width},${out.height}`]), `orientation ${o}`);
  }
  // A phone held upright (6): the top-left of the stored pixels ends up top-right.
  assert.deepEqual(apply(orientationMatrix(6, w, h), 0, 0), [h, 0]);
  // Upside down (3): top-left ends up bottom-right.
  assert.deepEqual(apply(orientationMatrix(3, w, h), 0, 0), [w, h]);
});

// ------------------------------------------------------------ sizing

test("large photos are scaled so the longest side fits; small ones are left alone", () => {
  // A 48 MP iPhone photo, a 24 MP one and a small screenshot.
  assert.deepEqual(pick(planRender({ width: 8064, height: 6048, upright: true }, 1, { maxEdge: 2048 })), { width: 2048, height: 1536 });
  assert.deepEqual(pick(planRender({ width: 4284, height: 5712, upright: true }, 1, { maxEdge: 2048 })), { width: 1536, height: 2048 });
  assert.deepEqual(pick(planRender({ width: 800, height: 600, upright: true }, 1, { maxEdge: 2048 })), { width: 800, height: 600 });
  assert.equal(planRender({ width: 8064, height: 6048, upright: true }, 1, { maxEdge: 3200 }).width, 3200);
});

test("a sideways phone photo is turned upright when the browser didn't do it", () => {
  // Stored 4032x3024 landscape, tagged 6: the photo is really portrait.
  const plan = planRender({ width: 4032, height: 3024, upright: false }, 6, { maxEdge: 2048 });
  assert.deepEqual(pick(plan), { width: 1536, height: 2048 });
  assert.equal(plan.drawWidth, 2048);
  assert.equal(plan.drawHeight, 1536);
  assert.deepEqual(plan.transform, orientationMatrix(6, 2048, 1536));
});

test("no second turn when the browser already applied the orientation", () => {
  const plan = planRender({ width: 3024, height: 4032, upright: true }, 6, { maxEdge: 2048 });
  assert.deepEqual(pick(plan), { width: 1536, height: 2048 });
  assert.equal(plan.transform, null);
});

const pick = ({ width, height }: { width: number; height: number }) => ({ width, height });

// ------------------------------------------------------------ preparePhoto

test("a 9 MB rotated phone JPEG comes back small, upright and named .jpg", async () => {
  const fake = fakeDeps({ width: 4032, height: 3024, upright: false });
  const result = await preparePhotoWith(fake.deps, fileOf(jpegWithOrientation(6), 9 * MB, "IMG_0042.JPG"), { maxEdge: 2048 });
  assert.equal(result.name, "IMG_0042.jpg");
  assert.equal(result.type, "image/jpeg");
  assert.ok(result.size < 1 * MB);
  assert.deepEqual(pick(fake.plan()!), { width: 1536, height: 2048 });
  assert.ok(fake.plan()!.transform);
  assert.equal(fake.closed(), 1, "the decoded bitmap is released");
});

test("HEIC falls back to the converter when the browser can't decode it", async () => {
  const fake = fakeDeps({ width: 4032, height: 3024, upright: false }, { nativeFails: true });
  const result = await preparePhotoWith(fake.deps, fileOf(HEIC), { maxEdge: 2048 });
  assert.deepEqual(fake.calls, ["readHead", "decode", "decodeHeic", "render"]);
  assert.equal(result.name, "IMG_1234.jpg");
  // libheif applies the HEIF rotation itself; EXIF isn't consulted for HEIC.
  assert.equal(fake.plan()!.transform, null);
  assert.equal(fake.plan()!.width, 2048);
});

test("HEIC the browser reads natively (Safari) skips the converter", async () => {
  const fake = fakeDeps({ width: 3024, height: 4032, upright: true });
  await preparePhotoWith(fake.deps, fileOf(HEIC), { maxEdge: 2048 });
  assert.deepEqual(fake.calls, ["readHead", "decode", "render"]);
});

test("a HEIC the converter can't read gets its own message", async () => {
  const fake = fakeDeps({ width: 1, height: 1, upright: true }, { nativeFails: true, heicFails: true });
  await assert.rejects(preparePhotoWith(fake.deps, fileOf(HEIC), { maxEdge: 2048 }), /couldn't convert that HEIC/);
});

test("files over 25 MB are refused before anything is read", async () => {
  const fake = fakeDeps({ width: 1, height: 1, upright: true });
  const huge = { size: PHOTO_PICK_MAX_BYTES + 1, name: "huge.jpg", slice: () => assert.fail("read") } as unknown as File;
  await assert.rejects(preparePhotoWith(fake.deps, huge, { maxEdge: 2048 }), (error: Error) => error.message === TOO_LARGE);
  assert.deepEqual(fake.calls, []);
  assert.equal(TOO_LARGE, "That file is too large; please choose a photo under 25 MB.");
  // Exactly 25 MB is fine.
  await preparePhotoWith(fake.deps, fileOf(PNG, PHOTO_PICK_MAX_BYTES), { maxEdge: 2048 });
});

test("non-images are refused without being decoded, whatever they're named", async () => {
  for (const [head, name] of [
    [new TextEncoder().encode("%PDF-1.7"), "trail-map.pdf"],
    [new TextEncoder().encode("hello, not a photo"), "renamed.jpg"],
    [new TextEncoder().encode("<svg xmlns="), "logo.png"],
    [AVIF, "photo.heic"],
  ] as const) {
    const fake = fakeDeps({ width: 1, height: 1, upright: true });
    await assert.rejects(preparePhotoWith(fake.deps, fileOf(head, 1000, name), { maxEdge: 2048 }), (error: Error) => error.message === NOT_A_PHOTO, name);
    assert.deepEqual(fake.calls, ["readHead"], name);
  }
});

test("a file that looks like a JPEG but won't decode is refused plainly", async () => {
  const fake = fakeDeps({ width: 1, height: 1, upright: true }, { nativeFails: true });
  await assert.rejects(preparePhotoWith(fake.deps, fileOf(jpegWithOrientation(1), 5000, "broken.jpg"), { maxEdge: 2048 }), (error: Error) => error.message === NOT_A_PHOTO);
  assert.deepEqual(fake.calls, ["readHead", "decode"]);
});

test("empty files and unexpected failures get plain messages", async () => {
  const fake = fakeDeps({ width: 1, height: 1, upright: true });
  await assert.rejects(preparePhotoWith(fake.deps, new File([], "empty.jpg"), { maxEdge: 2048 }), (error: Error) => error.message === EMPTY_FILE);
  assert.equal(photoProblemMessage(new Error("Canvas encode failed")), PREPARE_FAILED);
  assert.equal(photoProblemMessage(new DOMException("boom")), PREPARE_FAILED);
});
