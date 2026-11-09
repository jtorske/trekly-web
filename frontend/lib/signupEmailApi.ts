import { apiFetch } from "./api";

export type SignupEmailReason = "signup" | "resend";

/**
 * Ask the API to email whoever owns this address whatever helps them in:
 * the confirmation link again, "You already have a Trekly account", or
 * "You signed up with Google" (backend/app/routers/signup_email.py). The
 * answer is the same whether or not the address has an account; only a 429
 * (too many in an hour, same for every address) is an error worth showing.
 */
export async function requestSignupEmail(email: string, next: string, reason: SignupEmailReason): Promise<void> {
  await apiFetch("/api/auth/signup-email", { method: "POST", body: { email, next, reason } });
}
