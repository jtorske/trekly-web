/**
 * Getting a picked photo ready to upload, shared by every photo input
 * (avatars, gear, journal, admin trail photos). Phone photos are often
 * 8-12 MB, sometimes HEIC, and often stored sideways with an EXIF
 * orientation tag, so before the cropper or upload we:
 *
 *   1. refuse anything over 25 MB or that isn't really an image,
 *   2. decode it (HEIC through a WebAssembly fallback when the browser can't),
 *   3. apply the EXIF orientation, and
 *   4. scale it down and re-encode it as a metadata-free JPEG.
 *
 * This is for speed and convenience only. Storage policies and the API still
 * check the real content, type and size of what's stored (and the API strips
 * EXIF/GPS itself), so nothing here is a security boundary.
 *
 * The steps that touch the DOM are injected (see lib/preparePhoto.ts), so
 * this module runs, and is tested, in Node.
 */
import { photoSize } from "./journalPhoto.ts";
import { sniffPhotoType } from "./imageType.ts";

export const PHOTO_PICK_MAX_BYTES = 25 * 1024 * 1024;
/** For `<input type="file" accept>`; the extensions help browsers that don't know the HEIC types. */
export const PHOTO_ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";
export const PHOTO_HINT = "JPEG, PNG or HEIC, up to 25 MB";
export const PREPARING_PHOTO = "Preparing photo…";

export const TOO_LARGE = "That file is too large; please choose a photo under 25 MB.";
export const NOT_A_PHOTO = "That file isn't a photo we can read. Please choose a JPEG, PNG or HEIC photo.";
export const EMPTY_FILE = "That file is empty. Please choose another photo.";
export const PREPARE_FAILED = "We couldn't prepare that photo. Please try another one.";

/** Enough of the file for its type and the EXIF block (which sits near the start of a JPEG). */
export const HEAD_BYTES = 128 * 1024;

/** A problem with the picked file, worded for the person who picked it. */
export class PhotoProblem extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PhotoProblem";
  }
}

/** The message to show for anything preparePhoto throws. */
export function photoProblemMessage(error: unknown): string {
  return error instanceof PhotoProblem ? error.message : PREPARE_FAILED;
}

/** The checks that need no decoding: size first, so a huge file is never read. */
export function pickProblem(size: number, type: string | null): string | null {
  if (size === 0) return EMPTY_FILE;
  if (size > PHOTO_PICK_MAX_BYTES) return TOO_LARGE;
  if (!type) return NOT_A_PHOTO;
  return null;
}

// ---------------------------------------------------------------- orientation

export type Orientation = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

/**
 * The EXIF orientation of a JPEG (1 = upright), from its first bytes. Walks
 * the JPEG segments to the Exif APP1 block and reads tag 0x0112 from IFD0.
 */
export function readExifOrientation(bytes: Uint8Array): Orientation {
  if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return 1;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 2;
  while (offset + 4 <= bytes.length) {
    if (bytes[offset] !== 0xff) return 1;
    const marker = bytes[offset + 1];
    // Start of scan or end of image: no Exif block before the pixels.
    if (marker === 0xda || marker === 0xd9) return 1;
    const length = view.getUint16(offset + 2);
    const start = offset + 4;
    if (marker === 0xe1 && start + 14 <= bytes.length && String.fromCharCode(...bytes.slice(start, start + 4)) === "Exif") {
      return tiffOrientation(view, start + 6);
    }
    offset += 2 + length;
  }
  return 1;
}

function tiffOrientation(view: DataView, tiff: number): Orientation {
  try {
    const little = view.getUint16(tiff) === 0x4949; // "II"; "MM" is big-endian
    if (view.getUint16(tiff + 2, little) !== 42) return 1;
    const ifd = tiff + view.getUint32(tiff + 4, little);
    const entries = view.getUint16(ifd, little);
    for (let i = 0; i < entries; i++) {
      const entry = ifd + 2 + i * 12;
      if (view.getUint16(entry, little) === 0x0112) {
        const value = view.getUint16(entry + 8, little);
        return value >= 1 && value <= 8 ? (value as Orientation) : 1;
      }
    }
  } catch {
    // Truncated or malformed Exif: treat the photo as upright.
  }
  return 1;
}

/** Orientations 5-8 turn the picture a quarter turn, swapping width and height. */
export function orientedSize(width: number, height: number, orientation: Orientation) {
  return orientation >= 5 ? { width: height, height: width } : { width, height };
}

/** A canvas transform [a, b, c, d, e, f] (as for setTransform). */
export type Matrix = [number, number, number, number, number, number];

/**
 * The transform that draws an unrotated w x h source upright. Drawing the
 * source at (0, 0, w, h) under it fills (0, 0) to orientedSize(w, h).
 */
export function orientationMatrix(orientation: Orientation, w: number, h: number): Matrix {
  switch (orientation) {
    case 2: return [-1, 0, 0, 1, w, 0]; // mirrored
    case 3: return [-1, 0, 0, -1, w, h]; // upside down
    case 4: return [1, 0, 0, -1, 0, h]; // mirrored, upside down
    case 5: return [0, 1, 1, 0, 0, 0]; // mirrored, quarter turn
    case 6: return [0, 1, -1, 0, h, 0]; // phone held upright: quarter turn clockwise
    case 7: return [0, -1, -1, 0, h, w];
    case 8: return [0, -1, 1, 0, 0, w]; // quarter turn anticlockwise
    default: return [1, 0, 0, 1, 0, 0];
  }
}

// ---------------------------------------------------------------- preparing

/** A decoded image. `source` is whatever the renderer draws (an ImageBitmap in the browser). */
export interface DecodedPhoto {
  width: number;
  height: number;
  source: unknown;
  /** True when the decoder has already turned the pixels upright. */
  upright: boolean;
  close(): void;
}

export interface RenderPlan {
  /** The output canvas. */
  width: number;
  height: number;
  /** Where the source is drawn, before `transform`. */
  drawWidth: number;
  drawHeight: number;
  transform: Matrix | null;
  quality: number;
}

export interface PhotoDeps {
  readHead(file: Blob): Promise<Uint8Array>;
  /** The browser's own decoder; rejects for formats it can't read. */
  decode(file: Blob): Promise<DecodedPhoto>;
  /** The HEIC fallback, loaded only when it's needed. */
  decodeHeic(file: Blob): Promise<DecodedPhoto>;
  /** Encodes the plan as a JPEG. */
  render(photo: DecodedPhoto, plan: RenderPlan): Promise<Blob>;
}

export type PrepareOptions = {
  /** Longest side of the result in pixels; smaller photos aren't enlarged. */
  maxEdge: number;
  quality?: number;
};

/** The output size and transform for a decoded photo. */
export function planRender(
  decoded: { width: number; height: number; upright: boolean },
  orientation: Orientation,
  { maxEdge, quality = 0.9 }: PrepareOptions,
): RenderPlan {
  const turn: Orientation = decoded.upright ? 1 : orientation;
  const upright = orientedSize(decoded.width, decoded.height, turn);
  const size = photoSize(upright.width, upright.height, maxEdge);
  const scale = size.width / upright.width;
  const drawWidth = decoded.width * scale;
  const drawHeight = decoded.height * scale;
  return {
    ...size,
    drawWidth,
    drawHeight,
    transform: turn === 1 ? null : orientationMatrix(turn, drawWidth, drawHeight),
    quality,
  };
}

/**
 * Check, decode, turn upright and scale down a picked photo. Resolves to a
 * small JPEG File; throws a PhotoProblem with a message for the user.
 */
export async function preparePhotoWith(deps: PhotoDeps, file: Blob, options: PrepareOptions): Promise<File> {
  const early = pickProblem(file.size, "unchecked");
  if (early) throw new PhotoProblem(early);
  const head = await deps.readHead(file);
  const type = sniffPhotoType(head);
  const problem = pickProblem(file.size, type);
  if (problem) throw new PhotoProblem(problem);

  let decoded: DecodedPhoto;
  try {
    decoded = await deps.decode(file);
  } catch {
    // Safari reads HEIC itself; other browsers need the converter.
    if (type !== "image/heic") throw new PhotoProblem(NOT_A_PHOTO);
    try {
      decoded = await deps.decodeHeic(file);
    } catch {
      throw new PhotoProblem("We couldn't convert that HEIC photo. Please try a JPEG or PNG instead.");
    }
  }

  try {
    const orientation = type === "image/jpeg" ? readExifOrientation(head) : 1;
    const blob = await deps.render(decoded, planRender(decoded, orientation, options));
    const name = ((file as File).name || "photo").replace(/\.[^./\\]*$/, "") + ".jpg";
    return new File([blob], name, { type: blob.type || "image/jpeg" });
  } finally {
    decoded.close();
  }
}
