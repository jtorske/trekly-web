/** Inputs the journal accepts before resizing; anything bigger is likely not a photo. */
export const PHOTO_INPUT_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const PHOTO_INPUT_MAX_BYTES = 25 * 1024 * 1024;

export function photoInputProblem(file: { type: string; size: number }): string | null {
  if (!PHOTO_INPUT_TYPES.includes(file.type)) return "Use a JPEG, PNG or WebP photo.";
  if (file.size > PHOTO_INPUT_MAX_BYTES) return "That photo is over 25 MB. Try a smaller one.";
  return null;
}

/** Scale (width, height) down so the longer edge is at most `maxEdge`; never up. */
export function photoSize(width: number, height: number, maxEdge: number): { width: number; height: number } {
  const scale = Math.min(1, maxEdge / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}
