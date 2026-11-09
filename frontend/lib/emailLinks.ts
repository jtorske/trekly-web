/**
 * The links in Trekly's auth emails (supabase/templates/*.html) point at
 * /auth/confirm on our own site, never at supabase.co:
 *
 *   {{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=signup
 *
 * That page verifies the token hash in the browser (supabase.auth.verifyOtp),
 * which signs the person in, then sends them on. Pure helpers here so the
 * routing and error copy can be unit tested.
 */

export const CONFIRM_TYPES = ["signup", "invite", "magiclink", "recovery", "email_change", "email"] as const;
export type ConfirmType = (typeof CONFIRM_TYPES)[number];

export interface ConfirmLink {
  tokenHash: string;
  type: ConfirmType;
}

/** Reads token_hash and type from /auth/confirm's query string; null when either is missing or unknown. */
export function parseConfirmLink(search: string): ConfirmLink | null {
  const params = new URLSearchParams(search);
  const tokenHash = params.get("token_hash")?.trim() ?? "";
  const type = params.get("type") ?? "";
  if (!tokenHash || !(CONFIRM_TYPES as readonly string[]).includes(type)) return null;
  return { tokenHash, type: type as ConfirmType };
}

export const EMAIL_SETTINGS_PATH = "/settings/email-and-password";

/** Where each kind of link lands once it's verified. */
export function confirmDestination(type: ConfirmType): string {
  switch (type) {
    case "signup":
      return "/welcome";
    // An invited person has no password yet, so they choose one first too.
    case "invite":
    case "recovery":
      return "/reset-password";
    case "email_change":
      return EMAIL_SETTINGS_PATH;
    default:
      return "/profile";
  }
}

export interface LinkProblem {
  title: string;
  subtitle: string;
  action: { label: string; href: string };
}

/** What to show when a link can't be used: expired, already used, or cut short. */
export function confirmProblem(type: ConfirmType | null, signedIn: boolean): LinkProblem {
  const subtitle =
    type === null
      ? "Part of the link is missing. Try opening it again, or copy the whole link from the email into your browser."
      : "Links in Trekly emails work once and expire after an hour. This one has expired or was already used.";
  const title = type === null ? "This link is incomplete" : "This link has expired";
  switch (type) {
    case "recovery":
      return { title, subtitle, action: { label: "Send a new reset link", href: "/forgot-password" } };
    case "email_change":
      return {
        title,
        subtitle,
        action: signedIn
          ? { label: "Change your email again", href: EMAIL_SETTINGS_PATH }
          : { label: "Sign in", href: `/login?next=${encodeURIComponent(EMAIL_SETTINGS_PATH)}` },
      };
    case "signup":
      return {
        title,
        subtitle: signedIn
          ? "You're already signed in, so your email is confirmed. Carry on where you left off."
          : `${subtitle} Sign in and we can send a new confirmation link.`,
        action: signedIn ? { label: "Continue to Trekly", href: "/welcome" } : { label: "Sign in", href: "/login" },
      };
    default:
      return {
        title,
        subtitle,
        action: signedIn ? { label: "Continue to Trekly", href: "/profile" } : { label: "Sign in", href: "/login" },
      };
  }
}
