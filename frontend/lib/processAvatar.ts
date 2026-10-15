import { AVATAR_OUTPUT_SIZE, cropRect, type Offset } from "./avatarImage";

export type ProcessedAvatar = { blob: Blob; extension: "webp" | "jpg" };

/**
 * Crop the chosen square out of `file`, resize it to 512x512 and re-encode
 * it. Drawing through a canvas drops all metadata, so EXIF (including GPS
 * location) never leaves the device. createImageBitmap applies the EXIF
 * orientation first, so phone photos aren't sideways.
 */
export async function processAvatar(
  file: Blob,
  crop: { frame: number; zoom: number; offset: Offset },
): Promise<ProcessedAvatar> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    const { sx, sy, size } = cropRect({ width: bitmap.width, height: bitmap.height }, crop.frame, crop.zoom, crop.offset);
    const canvas = document.createElement("canvas");
    canvas.width = AVATAR_OUTPUT_SIZE;
    canvas.height = AVATAR_OUTPUT_SIZE;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Your browser couldn't process that photo.");
    context.imageSmoothingQuality = "high";
    context.drawImage(bitmap, sx, sy, size, size, 0, 0, AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE);

    const encode = (type: string) =>
      new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, 0.85));
    // Some browsers (older Safari) can't encode WebP and silently return PNG.
    const webp = await encode("image/webp");
    if (webp?.type === "image/webp") return { blob: webp, extension: "webp" };
    const jpeg = await encode("image/jpeg");
    if (jpeg) return { blob: jpeg, extension: "jpg" };
    throw new Error("Your browser couldn't process that photo.");
  } finally {
    bitmap.close();
  }
}
