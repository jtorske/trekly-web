import { HEAD_BYTES, preparePhotoWith, type DecodedPhoto, type PhotoDeps, type PrepareOptions } from "./photoPrep";

/** For the avatar cropper and the gear and journal photos (both then shrink to 1400px or less). */
export const PICK_EDGE = 2048;
/** Admin trail photos: the API makes a 1600px hero from this, so leave it room. */
export const TRAIL_PHOTO_EDGE = 3200;

// A 2x1 JPEG tagged EXIF orientation 6. Browsers that honour the tag decode it as 1x2.
const ORIENTATION_PROBE =
  "/9j/4AAQSkZJRgABAQAAAQABAAD/4QAiRXhpZgAATU0AKgAAAAgAAQESAAMAAAABAAYAAAAAAAD/2wBDAFA3PEY8MlBGQUZaVVBfeMiCeG5uePWvuZHI////////////////////////////////////////////////////2wBDAVVaWnhpeOuCguv/////////////////////////////////////////////////////////////////////////wAARCAABAAIDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAgT/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCQAKH/2Q==";

let honoursOrientation: Promise<boolean> | null = null;

/** Whether createImageBitmap turns EXIF-rotated photos upright (checked once). */
function bitmapsHonourOrientation(): Promise<boolean> {
  honoursOrientation ??= (async () => {
    try {
      const bytes = Uint8Array.from(atob(ORIENTATION_PROBE), (char) => char.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/jpeg" }), { imageOrientation: "from-image" });
      const upright = bitmap.width === 1 && bitmap.height === 2;
      bitmap.close();
      return upright;
    } catch {
      return false;
    }
  })();
  return honoursOrientation;
}

function fromBitmap(bitmap: ImageBitmap, upright: boolean): DecodedPhoto {
  return { width: bitmap.width, height: bitmap.height, source: bitmap, upright, close: () => bitmap.close() };
}

const browserDeps: PhotoDeps = {
  readHead: async (file) => new Uint8Array(await file.slice(0, HEAD_BYTES).arrayBuffer()),

  decode: async (file) => {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    return fromBitmap(bitmap, await bitmapsHonourOrientation());
  },

  decodeHeic: async (file) => {
    // About 760 KB gzipped (libheif in WebAssembly, run in a worker), so it's
    // only fetched when someone picks a HEIC their browser can't read itself.
    const { heicTo } = await import("heic-to/next");
    // libheif applies the HEIF rotation itself (HEIC ignores EXIF orientation).
    return fromBitmap(await heicTo({ blob: file, type: "bitmap" }), true);
  },

  render: async (photo, plan) => {
    const canvas = document.createElement("canvas");
    canvas.width = plan.width;
    canvas.height = plan.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("No 2D canvas");
    // JPEG has no transparency; a transparent PNG would otherwise turn black.
    context.fillStyle = "#fff";
    context.fillRect(0, 0, plan.width, plan.height);
    if (plan.transform) context.setTransform(...plan.transform);
    context.imageSmoothingQuality = "high";
    context.drawImage(photo.source as CanvasImageSource, 0, 0, plan.drawWidth, plan.drawHeight);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", plan.quality));
    // Free the canvas memory straight away (iOS Safari caps the total).
    canvas.width = canvas.height = 0;
    if (!blob) throw new Error("Canvas encode failed");
    return blob;
  },
};

/**
 * Check a picked photo and turn it into an upright, metadata-free JPEG no
 * bigger than `maxEdge` on its longest side. Throws a PhotoProblem (see
 * photoProblemMessage) when the file is too large or isn't a photo.
 */
export function preparePhoto(file: File, options: PrepareOptions = { maxEdge: PICK_EDGE }): Promise<File> {
  return preparePhotoWith(browserDeps, file, options);
}
