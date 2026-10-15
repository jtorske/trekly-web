import type { Profile, ProfileUpdate } from "@/lib/accountApi";

export const BIO_LIMIT = 280;

export type ProfileFormValues = {
  display_name: string;
  username: string;
  bio: string;
  home_region: string;
};

export function initialValues(profile: Profile): ProfileFormValues {
  return {
    display_name: profile.display_name ?? "",
    username: profile.username ?? "",
    bio: profile.bio ?? "",
    home_region: profile.home_region ?? "",
  };
}

export function isDirty(
  values: ProfileFormValues,
  initial: ProfileFormValues,
  avatar: { file: unknown; remove: boolean },
): boolean {
  return JSON.stringify(values) !== JSON.stringify(initial) || avatar.file != null || avatar.remove;
}

/** Field errors keyed by field name; empty when the values can be saved. */
export function validateProfile(values: ProfileFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  const username = values.username.trim().toLowerCase();
  if (username && !/^[a-z0-9_]{3,30}$/.test(username)) {
    errors.username = "Use 3–30 lowercase letters, numbers or underscores.";
  }
  if (values.bio.length > BIO_LIMIT) errors.bio = `Keep your bio to ${BIO_LIMIT} characters.`;
  return errors;
}

/** The text fields as the API expects them: trimmed, with blanks cleared. */
export function profileUpdate(values: ProfileFormValues): ProfileUpdate {
  return {
    display_name: values.display_name.trim() || null,
    username: values.username.trim().toLowerCase() || null,
    bio: values.bio.trim() || null,
    home_region: values.home_region.trim() || null,
  };
}

/** What a close request (Cancel, ×, Escape, backdrop) should do. */
export function closeAction(state: { dirty: boolean; confirming: boolean }): "close" | "confirm" | "keep-editing" {
  if (state.confirming) return "keep-editing";
  return state.dirty ? "confirm" : "close";
}
