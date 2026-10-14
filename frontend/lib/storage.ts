import { getSupabaseClient } from "./supabaseClient";

/**
 * Private Supabase Storage buckets (see migrations c3d4e5f6a7b8, e5f6a7b8c9d0).
 * Policies only allow a user to read, upload or delete objects under a
 * folder named after their own user id.
 */
export type Bucket = "gear-photos" | "avatars";

const LIMITS: Record<Bucket, number> = {
  "gear-photos": 5 * 1024 * 1024,
  avatars: 2 * 1024 * 1024,
};
const EXTENSIONS: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
};

export function validateImage(file: File, bucket: Bucket): string | null {
  if (!EXTENSIONS[file.type]) return "Use a JPEG, PNG or WebP image.";
  if (file.size > LIMITS[bucket]) {
    return `Images must be ${LIMITS[bucket] / 1024 / 1024} MB or smaller.`;
  }
  return null;
}

export async function uploadImage(bucket: Bucket, userId: string, file: File): Promise<string> {
  const problem = validateImage(file, bucket);
  if (problem) throw new Error(problem);
  const path = `${userId}/${crypto.randomUUID()}.${EXTENSIONS[file.type]}`;
  const { error } = await getSupabaseClient()
    .storage.from(bucket)
    .upload(path, file, { contentType: file.type, upsert: false });
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
