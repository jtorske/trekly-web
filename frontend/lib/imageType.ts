/**
 * What an image file really is, from its first bytes. The browser's
 * `File.type` only reflects the file name, so a text file renamed to .jpg
 * claims to be image/jpeg.
 */

export type ImageType = "image/jpeg" | "image/png" | "image/webp";

export const NOT_AN_IMAGE = "We couldn't read that image. Choose a JPEG, PNG or WebP photo.";

const startsWith = (bytes: Uint8Array, signature: number[], offset = 0) =>
  bytes.length >= offset + signature.length && signature.every((byte, i) => bytes[offset + i] === byte);

const ascii = (text: string) => [...text].map((char) => char.charCodeAt(0));

export function sniffImageType(bytes: Uint8Array): ImageType | null {
  if (startsWith(bytes, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (startsWith(bytes, ascii("RIFF")) && startsWith(bytes, ascii("WEBP"), 8)) return "image/webp";
  return null;
}

export async function readImageType(file: Blob): Promise<ImageType | null> {
  try {
    return sniffImageType(new Uint8Array(await file.slice(0, 12).arrayBuffer()));
  } catch {
    return null;
  }
}
