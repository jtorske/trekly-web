import { NOT_AN_IMAGE, readImageType } from "./imageType";
import { processPhoto } from "./processPhoto";
import { getSupabaseClient } from "./supabaseClient";

/**
 * Supabase Storage buckets (see migrations c3d4e5f6a7b8, e5f6a7b8c9d0,
 * 9a769eeb0dae, 739722285c4e, 214aa07bf743). Policies only allow a user to
 * upload, list or delete objects under a folder named after their own user
 * id, and every bucket only takes processed (re-encoded, metadata-free)
 * WebP/JPEG images. gear-photos and hike-photos are private (signed URLs,
 * which visitors can also get for photos in a public profile section);
 * avatars are publicly readable by URL.
 */
export type Bucket = "gear-photos" | "avatars" | "hike-photos";

const LIMITS: Record<Bucket, number> = {
  // The photo picked; it's resized to fit 1 MB before upload (lib/processPhoto.ts).
  "gear-photos": 5 * 1024 * 1024,
  // Processed 512px avatars only; see lib/avatarImage.ts for the input limit.
  avatars: 1024 * 1024,
  // Processed journal photos only; see lib/processPhoto.ts.
  "hike-photos": 1024 * 1024,
};
const EXTENSIONS: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
};

/** Checks the name-based type and size, then the file's actual contents. */
export async function validateImage(file: File, bucket: Bucket): Promise<string | null> {
  if (!EXTENSIONS[file.type]) return "Use a JPEG, PNG or WebP image.";
  if (file.size > LIMITS[bucket]) {
    return `Images must be ${LIMITS[bucket] / 1024 / 1024} MB or smaller.`;
  }
  if (!(await readImageType(file))) return NOT_AN_IMAGE;
  return null;
}

export async function uploadImage(bucket: Bucket, userId: string, file: File): Promise<string> {
  const problem = await validateImage(file, bucket);
  if (problem) throw new Error(problem);
  // Re-encoding through a canvas drops EXIF, so a phone photo's GPS
  // location never leaves the device (gear can be shown on a public profile).
  const image = await processPhoto(file);
  const path = `${userId}/${crypto.randomUUID()}.${image.extension}`;
  const { error } = await getSupabaseClient()
    .storage.from(bucket)
    .upload(path, image.blob, { contentType: image.blob.type, upsert: false });
  if (error) throw new Error(`Upload failed: ${error.message}`);
  return path;
}

export async function removeImages(bucket: Bucket, paths: string[]): Promise<void> {
  if (paths.length === 0) return;
  await getSupabaseClient().storage.from(bucket).remove(paths);
}

/** Every object in the user's own folder (used before account deletion). */
export async function listOwnImages(bucket: Bucket, userId: string): Promise<string[]> {
  const { data, error } = await getSupabaseClient().storage.from(bucket).list(userId, { limit: 1000 });
  if (error || !data) return [];
  return data.map((object) => `${userId}/${object.name}`);
}

const signedUrlCache = new Map<string, { url: string; expires: number }>();
const SIGNED_URL_SECONDS = 60 * 60;

export async function signedImageUrl(bucket: Bucket, path: string): Promise<string | null> {
  const key = `${bucket}:${path}`;
  const cached = signedUrlCache.get(key);
  if (cached && cached.expires > Date.now() + 60_000) return cached.url;
  const { data, error } = await getSupabaseClient()
    .storage.from(bucket)
    .createSignedUrl(path, SIGNED_URL_SECONDS);
  if (error || !data?.signedUrl) return null;
  signedUrlCache.set(key, { url: data.signedUrl, expires: Date.now() + SIGNED_URL_SECONDS * 1000 });
  return data.signedUrl;
}

/** Avatars never change in place (each change is a new path), so this URL is cache-safe. */
export function publicAvatarUrl(path: string): string {
  return getSupabaseClient().storage.from("avatars").getPublicUrl(path).data.publicUrl;
}

/** Upload a processed journal photo to `{userId}/{uuid}.{ext}` in the private hike-photos bucket. */
export async function uploadHikePhoto(userId: string, image: { blob: Blob; extension: "webp" | "jpg" }): Promise<string> {
  const path = `${userId}/${crypto.randomUUID()}.${image.extension}`;
  const { error } = await getSupabaseClient()
    .storage.from("hike-photos")
    .upload(path, image.blob, { contentType: image.blob.type, upsert: false });
  if (error) throw new Error(`Upload failed: ${error.message}`);
  return path;
}

/**
 * Upload a processed avatar to `{userId}/{uuid}.{ext}` and report progress
 * (0-1). supabase-js has no progress events, so this calls the Storage REST
 * endpoint directly with the user's session token.
 */
export async function uploadAvatar(
  userId: string,
  image: { blob: Blob; extension: "webp" | "jpg" },
  onProgress: (fraction: number) => void,
): Promise<string> {
  const supabase = getSupabaseClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Your session has expired. Sign in again to upload a photo.");
  const path = `${userId}/${crypto.randomUUID()}.${image.extension}`;
  const url = `${process.env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/object/avatars/${path}`;

  await new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", url);
    request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.setRequestHeader("apikey", process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "");
    request.setRequestHeader("Content-Type", image.blob.type);
    request.setRequestHeader("x-upsert", "false");
    request.setRequestHeader("cache-control", "max-age=31536000");
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(1);
        resolve();
        return;
      }
      let message = `status ${request.status}`;
      try {
        message = JSON.parse(request.responseText).message ?? message;
      } catch {
        // Not JSON; keep the status.
      }
      reject(new Error(`Upload failed: ${message}`));
    };
    request.onerror = () => reject(new Error("Upload failed. Check your connection and try again."));
    request.send(image.blob);
  });
  return path;
}
