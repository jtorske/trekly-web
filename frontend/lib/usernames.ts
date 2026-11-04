/**
 * Usernames: every account has one (it's the profile's address, /u/name).
 * The rules live on the server (backend/app/usernames.py, the reserved list in
 * backend/config/reserved_usernames.txt, and the database); the forms only
 * pre-check the format so they don't ask the API about obvious typos. The
 * API calls are in accountApi.ts.
 */

export const USERNAME_FORMAT = /^[a-z0-9_]{3,30}$/;
export const FORMAT_MESSAGE = "Use 3–30 lowercase letters, numbers or underscores.";

export function normalizeUsername(value: string): string {
  return value.trim().toLowerCase();
}

/** The format problem with a (normalized) username, or null if it's worth asking the server. */
export function formatProblem(username: string): string | null {
  if (!username) return "Choose a username.";
  return USERNAME_FORMAT.test(username) ? null : FORMAT_MESSAGE;
}

export type UsernameStatus = {
  state: "empty" | "invalid" | "checking" | "available" | "taken" | "unchecked" | "current";
  message: string;
};

/**
 * Whether a form may go ahead with this username. "unchecked" means the API
 * couldn't be asked; "current" is the name the account already has. The save
 * is checked again server-side either way.
 */
export function usernameReady(status: UsernameStatus): boolean {
  return status.state === "available" || status.state === "unchecked" || status.state === "current";
}

/** What to base a suggested username on: the display name, else the email. */
export function suggestionHint(displayName: string | null | undefined, email: string | null | undefined): string {
  const name = (displayName ?? "").trim();
  if (name) return name;
  return (email ?? "").trim();
}
