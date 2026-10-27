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
  state: "empty" | "invalid" | "checking" | "available" | "taken" | "unchecked";
  message: string;
};

/**
 * Whether a form may go ahead with this username. "unchecked" means the API
 * couldn't be asked; the save is checked again server-side either way.
 */
export function usernameReady(status: UsernameStatus): boolean {
  return status.state === "available" || status.state === "unchecked";
}

/** Sign-up user metadata; the new-user trigger reads `username` and `display_name`. */
export function signUpMetadata(displayName: string, username: string): Record<string, string> {
  const name = displayName.trim().slice(0, 60);
  return { username: normalizeUsername(username), ...(name ? { display_name: name } : {}) };
}

/** What to base a suggested username on: the display name, else the email. */
export function suggestionHint(displayName: string | null | undefined, email: string | null | undefined): string {
  const name = (displayName ?? "").trim();
  if (name) return name;
  return (email ?? "").trim();
}

/** Pages a signed-in user without a username can still open: sign-in plumbing and the legal pages. */
const OPEN_PATHS = ["/auth", "/login", "/signup", "/forgot-password", "/reset-password", "/privacy", "/terms"];

export function pathIsOpen(pathname: string): boolean {
  return OPEN_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export type GateState = "pass" | "wait" | "choose";

/**
 * Whether the app can be shown, or the "Choose your username" step must come
 * first. While a signed-in user's profile loads, wait (unless this browser
 * already saw them with a username), so no app page flashes up first. If the
 * profile can't load at all, don't lock them out of a broken API.
 */
export function usernameGate(input: {
  authStatus: "loading" | "signedOut" | "signedIn" | "unconfigured";
  pathname: string;
  profileLoading: boolean;
  profileError: string | null;
  username: string | null | undefined;
  knownToHaveUsername: boolean;
}): GateState {
  if (input.authStatus !== "signedIn" || pathIsOpen(input.pathname)) return "pass";
  if (input.profileLoading) return input.knownToHaveUsername ? "pass" : "wait";
  if (input.profileError) return "pass";
  return input.username ? "pass" : "choose";
}
