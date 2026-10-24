/**
 * Pure auth helpers (no React, no network) so they can be unit tested.
 */

export const DEFAULT_AFTER_LOGIN = "/profile";
export const PASSWORD_MIN_LENGTH = 8;

/**
 * Only same-site relative paths are allowed as post-auth redirects, so a
 * crafted ?next= link can't send users to another origin.
 */
export function safeNextPath(next: string | null | undefined, fallback = DEFAULT_AFTER_LOGIN): string {
  if (!next) return fallback;
  let decoded = next;
  try {
    decoded = decodeURIComponent(next);
  } catch {
    return fallback;
  }
  if (
    !decoded.startsWith("/") ||
    decoded.startsWith("//") ||
    decoded.startsWith("/\\") ||
    /[\u0000-\u001f]/.test(decoded) ||
    /^\/(login|signup|auth\/callback)(\/|\?|$)/.test(decoded)
  ) {
    return fallback;
  }
  return decoded;
}

/** `?next=` suffix for links into auth pages that should come back here. */
export function nextQuery(path: string): string {
  return `?next=${encodeURIComponent(path)}`;
}

export interface PasswordCheck {
  label: string;
  met: boolean;
}

export function passwordChecks(password: string): PasswordCheck[] {
  return [
    { label: `At least ${PASSWORD_MIN_LENGTH} characters`, met: password.length >= PASSWORD_MIN_LENGTH },
    { label: "Contains a letter", met: /[A-Za-z]/.test(password) },
    { label: "Contains a number or symbol", met: /[^A-Za-z]/.test(password) },
  ];
}

export function passwordIsValid(password: string): boolean {
  return passwordChecks(password).every((check) => check.met);
}

export function emailLooksValid(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

/**
 * Map provider errors to messages that help without revealing whether an
 * account exists for a given email.
 */
export function friendlyAuthError(error: unknown): string {
  const raw = error instanceof Error ? error.message : typeof error === "string" ? error : "";
  const code = (error as { code?: string } | null)?.code ?? "";
  const message = raw.toLowerCase();

  if (code === "invalid_credentials" || message.includes("invalid login credentials")) {
    return "That email and password don't match. Check them and try again.";
  }
  if (code === "email_not_confirmed" || message.includes("email not confirmed")) {
    return "Confirm your email before signing in. We can send the link again.";
  }
  if (code === "weak_password" || message.includes("password should")) {
    return `Choose a stronger password: at least ${PASSWORD_MIN_LENGTH} characters with a letter and a number or symbol.`;
  }
  if (code === "same_password" || message.includes("different from the old password")) {
    return "Your new password must be different from your current one.";
  }
  if (code === "over_email_send_rate_limit" || message.includes("rate limit") || code === "over_request_rate_limit") {
    return "Too many attempts. Wait a minute and try again.";
  }
  if (code === "reauthentication_needed" || message.includes("reauthentication")) {
    return "For security, confirm it's you with the code we just emailed.";
  }
  if (code === "otp_expired" || message.includes("expired") || message.includes("invalid") && message.includes("link")) {
    return "This link is invalid or has expired. Request a new one.";
  }
  if (code === "access_denied" && !message.includes("link")) {
    // The person backed out of the Google consent screen.
    return "Google sign-in was cancelled. Try again, or use your email and password.";
  }
  if (code === "provider_disabled" || message.includes("provider is not enabled")) {
    return "Google sign-in isn't available right now. Use your email and password instead.";
  }
  if (message.includes("failed to fetch") || message.includes("network")) {
    return "We couldn't reach the sign-in service. Check your connection and try again.";
  }
  if (message.includes("missing next_public_supabase")) {
    return "Sign-in isn't configured for this site yet.";
  }
  return raw || "Something went wrong. Please try again.";
}

/** Reads `error_description` from an auth redirect's query string or hash. */
export function authRedirectError(search: string, hash: string): string | null {
  for (const source of [search, hash.replace(/^#/, "?")]) {
    const params = new URLSearchParams(source);
    const description = params.get("error_description");
    const code = params.get("error_code") ?? params.get("error");
    if (description || code) {
      return friendlyAuthError(Object.assign(new Error(description ?? code ?? ""), { code: code ?? "" }));
    }
  }
  return null;
}
