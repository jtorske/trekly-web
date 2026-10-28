import type { Profile, ProfileUpdate } from "@/lib/accountApi";
import { formatProblem, normalizeUsername } from "../../lib/usernames.ts";

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

/** The photo isn't part of this: it saves on its own (ProfilePhoto). */
export function isDirty(values: ProfileFormValues, initial: ProfileFormValues): boolean {
  return JSON.stringify(values) !== JSON.stringify(initial);
}

/** Field errors keyed by field name; empty when the values can be saved. */
export function validateProfile(values: ProfileFormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  // Every account keeps a username; it can change but not be removed.
  const usernameProblem = formatProblem(normalizeUsername(values.username));
  if (usernameProblem) errors.username = usernameProblem;
  if (values.bio.length > BIO_LIMIT) errors.bio = `Keep your bio to ${BIO_LIMIT} characters.`;
  return errors;
}

/** The text fields as the API expects them: trimmed, with blanks cleared. */
export function profileUpdate(values: ProfileFormValues): ProfileUpdate {
  return {
    display_name: values.display_name.trim() || null,
    username: normalizeUsername(values.username),
    bio: values.bio.trim() || null,
    home_region: values.home_region.trim() || null,
  };
}
