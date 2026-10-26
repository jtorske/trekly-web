import { photoSize } from "./journalPhoto";

export type ProcessedPhoto = { blob: Blob; extension: "webp" | "jpg" };

/**
 * Resize a journal photo to fit PHOTO_MAX_EDGE and re-encode it. Drawing
 * through a canvas drops all metadata, so EXIF (including the GPS location
 * of a trail photo) never leaves the device. createImageBitmap applies the
 * EXIF orientation first, so phone photos aren't sideways.
 */
export async function processPhoto(file: Blob): Promise<ProcessedPhoto> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new Error("We couldn't read that image. Try a JPEG, PNG or WebP photo.");
  }
  try {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Your browser couldn't process that photo.");
    // Step down until it fits the bucket's 1 MB limit.
    for (const [edge, quality] of [[1400, 0.82], [1100, 0.78], [800, 0.72]] as const) {
      const { width, height } = photoSize(bitmap.width, bitmap.height, edge);
      canvas.width = width;
      canvas.height = height;
      context.imageSmoothingQuality = "high";
      context.drawImage(bitmap, 0, 0, width, height);
      const encode = (type: string) => new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, quality));
      // Some browsers (older Safari) can't encode WebP and silently return PNG.
      const webp = await encode("image/webp");
      const image: ProcessedPhoto | null =
        webp?.type === "image/webp" ? { blob: webp, extension: "webp" } : await encode("image/jpeg").then((jpeg) => (jpeg ? { blob: jpeg, extension: "jpg" as const } : null));
      if (!image) break;
      if (image.blob.size <= 1024 * 1024) return image;
    }
    throw new Error("Your browser couldn't process that photo.");
  } finally {
    bitmap.close();
  }
}
