/**
 * Avatar input rules and crop geometry. Pure functions (no DOM) so they can
 * be unit-tested; the canvas work lives in processAvatar.ts.
 */

export const AVATAR_INPUT_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
/** Limit on the photo the user picks. What's uploaded is a ~512px re-encode. */
export const AVATAR_MAX_INPUT_BYTES = 5 * 1024 * 1024;
export const AVATAR_OUTPUT_SIZE = 512;
export const MAX_ZOOM = 4;

export function validateAvatarFile(file: { type: string; size: number }): string | null {
  if (!(AVATAR_INPUT_TYPES as readonly string[]).includes(file.type)) {
    return "That file type isn't supported. Choose a JPEG, PNG or WebP image.";
  }
  if (file.size > AVATAR_MAX_INPUT_BYTES) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    return `That photo is ${mb} MB. Choose one that's 5 MB or smaller.`;
  }
  if (file.size === 0) return "That file is empty. Choose another photo.";
  return null;
}

export type Size = { width: number; height: number };
export type Offset = { x: number; y: number };

/** Displayed scale of the image inside a square frame of side `frame` at `zoom` (1 = cover). */
export function displayScale(image: Size, frame: number, zoom: number): number {
  return (frame / Math.min(image.width, image.height)) * zoom;
}

/**
 * Keep the image covering the whole frame. `offset` is how far the image
 * centre sits from the frame centre, in frame pixels.
 */
export function clampOffset(image: Size, frame: number, zoom: number, offset: Offset): Offset {
  const scale = displayScale(image, frame, zoom);
  const maxX = Math.max(0, (image.width * scale - frame) / 2);
  const maxY = Math.max(0, (image.height * scale - frame) / 2);
  const clamp = (value: number, max: number) => Math.min(max, Math.max(-max, value)) || 0;
  return { x: clamp(offset.x, maxX), y: clamp(offset.y, maxY) };
}

export function clampZoom(zoom: number): number {
  return Math.min(MAX_ZOOM, Math.max(1, zoom));
}

/** The square of the source image (in image pixels) visible in the frame. */
export function cropRect(image: Size, frame: number, zoom: number, offset: Offset) {
  const scale = displayScale(image, frame, zoom);
  const { x, y } = clampOffset(image, frame, zoom, offset);
  const size = frame / scale;
  return {
    sx: (image.width * scale - frame) / 2 / scale - x / scale,
    sy: (image.height * scale - frame) / 2 / scale - y / scale,
    size,
  };
}
