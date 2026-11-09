/**
 * What an image file really is, from its first bytes. The browser's
 * `File.type` only reflects the file name, so a text file renamed to .jpg
 * claims to be image/jpeg.
 */

export type ImageType = "image/jpeg" | "image/png" | "image/webp";

export const NOT_AN_IMAGE = "That file isn't a photo we can read. Please choose a JPEG, PNG or HEIC photo.";

const startsWith = (bytes: Uint8Array, signature: number[], offset = 0) =>
  bytes.length >= offset + signature.length && signature.every((byte, i) => bytes[offset + i] === byte);

const ascii = (text: string) => [...text].map((char) => char.charCodeAt(0));

export function sniffImageType(bytes: Uint8Array): ImageType | null {
  if (startsWith(bytes, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (startsWith(bytes, ascii("RIFF")) && startsWith(bytes, ascii("WEBP"), 8)) return "image/webp";
  return null;
}

/**
 * HEIC/HEIF (iPhone photos): an ISO-BMFF `ftyp` box whose major brand is
 * one of the HEIF image brands. AVIF uses the same box but brand "avif".
 */
const HEIF_BRANDS = new Set(["heic", "heix", "heim", "heis", "hevc", "hevx", "mif1", "msf1"]);

export function isHeif(bytes: Uint8Array): boolean {
  if (!startsWith(bytes, ascii("ftyp"), 4) || bytes.length < 12) return false;
  return HEIF_BRANDS.has(String.fromCharCode(...bytes.slice(8, 12)));
}

/** What a picked photo is: the upload types, or HEIC to convert first. */
export function sniffPhotoType(bytes: Uint8Array): ImageType | "image/heic" | null {
  return sniffImageType(bytes) ?? (isHeif(bytes) ? "image/heic" : null);
}

export async function readImageType(file: Blob): Promise<ImageType | null> {
  try {
    return sniffImageType(new Uint8Array(await file.slice(0, 12).arrayBuffer()));
  } catch {
    return null;
  }
}
