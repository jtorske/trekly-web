/**
 * Avatar crop geometry. Pure functions (no DOM) so they can
 * be unit-tested; the canvas work lives in processAvatar.ts. Picked photos
 * are checked and resized first by lib/photoPrep.ts.
 */

export const AVATAR_OUTPUT_SIZE = 512;
export const MAX_ZOOM = 4;

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
