import type { Profile, ProfileUpdate } from "./accountApi";
import type { ProcessedAvatar } from "./processAvatar";

/**
 * Changing or removing the profile photo, saved straight away. The steps
 * are injected so the order (and the cleanup when one fails) can be tested
 * without Storage or the API; see avatarSteps() in ProfilePhoto.tsx.
 *
 * Every photo is a new object under `{userId}/` in the avatars bucket, so
 * a change is: upload the new one, point the profile at it, then delete
 * the old one. Storage policies only let users write and delete in their
 * own folder, and the API only accepts avatar paths in the caller's folder.
 */
export interface AvatarSteps {
  upload: (image: ProcessedAvatar, onProgress: (fraction: number) => void) => Promise<string>;
  update: (update: ProfileUpdate) => Promise<Profile>;
  /** Must throw unless every path was really deleted (see deleteImages). */
  remove: (paths: string[]) => Promise<void>;
  announce: (profile: Profile) => void;
}

export const REMOVE_FAILED =
  "Your photo is off your profile, but its file couldn't be deleted from storage. Try removing it again.";

/** Upload `image` as the new photo. The old file is deleted once nothing points at it. */
export async function replaceAvatar(
  steps: AvatarSteps,
  previous: string | null,
  image: ProcessedAvatar,
  onProgress: (fraction: number) => void = () => undefined,
): Promise<Profile> {
  const uploaded = await steps.upload(image, onProgress);
  let saved: Profile;
  try {
    saved = await steps.update({ avatar_path: uploaded });
  } catch (error) {
    // Nothing points at the new upload, so don't leave it behind.
    await steps.remove([uploaded]).catch(() => undefined);
    throw error;
  }
  steps.announce(saved);
  // The new photo is saved either way; an old file left behind is only clutter.
  if (previous && previous !== saved.avatar_path) await steps.remove([previous]).catch(() => undefined);
  return saved;
}

/**
 * Clear the photo, then delete its file. Clearing first means the profile
 * never points at a deleted file; if the delete fails, the error says so
 * and `retryPath` lets the caller try the delete again.
 */
export async function removeAvatar(steps: AvatarSteps, previous: string): Promise<Profile> {
  const saved = await steps.update({ avatar_path: null });
  steps.announce(saved);
  try {
    await steps.remove([previous]);
  } catch {
    throw new AvatarCleanupError(previous);
  }
  return saved;
}

/** The profile change saved, but the old file is still in Storage. */
export class AvatarCleanupError extends Error {
  readonly retryPath: string;

  constructor(retryPath: string) {
    super(REMOVE_FAILED);
    this.name = "AvatarCleanupError";
    this.retryPath = retryPath;
  }
}

/**
 * Supabase Storage answers a delete it isn't allowed to do (or of a file
 * that isn't there) with success and an empty list, so check which of the
 * requested paths actually came back as deleted.
 */
export function undeletedPaths(requested: string[], deleted: { name: string }[] | null | undefined): string[] {
  const names = new Set((deleted ?? []).map((object) => object.name));
  return requested.filter((path) => !names.has(path));
}
