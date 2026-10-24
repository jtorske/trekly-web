"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import {
  emailLooksValid,
  friendlyAuthError,
  nextQuery,
  passwordChecks,
  passwordIsValid,
  safeNextPath,
} from "@/lib/authLogic";
import { getSupabaseClient } from "@/lib/supabaseClient";
import styles from "./AuthForm.module.css";

type Mode = "login" | "signup";

const RESEND_COOLDOWN_SECONDS = 60;

function callbackUrl(next: string): string {
  return `${window.location.origin}/auth/callback${nextQuery(next)}`;
}

export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>{title}</h1>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        {children}
      </div>
    </main>
  );
}

function useCooldown() {
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until <= now) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [until, now]);
  const remaining = Math.max(0, Math.ceil((until - now) / 1000));
  return { remaining, start: () => { setNow(Date.now()); setUntil(Date.now() + RESEND_COOLDOWN_SECONDS * 1000); } };
}

/** Resend the signup confirmation email, with a cooldown against spamming. */
export function ResendConfirmation({ email, next }: { email: string; next: string }) {
  const cooldown = useCooldown();
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [sending, setSending] = useState(false);

  const resend = async () => {
    setSending(true);
    setStatus(null);
    try {
      const { error } = await getSupabaseClient().auth.resend({
        type: "signup",
        email,
        options: { emailRedirectTo: callbackUrl(next) },
      });
      if (error) throw error;
      cooldown.start();
      setStatus({ ok: true, message: "If that address needs confirming, a new link is on its way." });
    } catch (error) {
      setStatus({ ok: false, message: friendlyAuthError(error) });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={styles.resend}>
      <button type="button" className={ui.secondary} onClick={resend} disabled={sending || cooldown.remaining > 0}>
        {sending ? "Sending…" : cooldown.remaining > 0 ? `Resend in ${cooldown.remaining}s` : "Resend confirmation email"}
      </button>
      {status && (
        <p className={status.ok ? ui.success : ui.error} role="status">
          {status.message}
        </p>
      )}
    </div>
  );
}

/**
 * Google OAuth. Supabase redirects to Google and back to /auth/callback, which
 * exchanges the PKCE code for a session. The same button signs up a new
 * person and signs in a returning one; a Google account with the same verified
 * email as an existing password account is linked to it by Supabase.
 */
function GoogleButton({ next, disabled, onError }: { next: string; disabled: boolean; onError: (message: string) => void }) {
  const [redirecting, setRedirecting] = useState(false);

  const start = async () => {
    setRedirecting(true);
    try {
      const { error } = await getSupabaseClient().auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: callbackUrl(next) },
      });
      if (error) throw error;
      // The browser is navigating to Google; leave the button in its busy state.
    } catch (caught) {
      onError(friendlyAuthError(caught));
      setRedirecting(false);
    }
  };

  return (
    <button type="button" className={styles.google} onClick={start} disabled={disabled || redirecting}>
      <svg aria-hidden="true" viewBox="0 0 18 18" width="18" height="18">
        <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
        <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z" />
        <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.05l3.01-2.33Z" />
        <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z" />
      </svg>
      {redirecting ? "Opening Google…" : "Continue with Google"}
    </button>
  );
}

export default function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status } = useAuth();
  const nextPath = safeNextPath(searchParams.get("next"));
  const carryNext = searchParams.get("next") ? nextQuery(nextPath) : "";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  // Already signed in (e.g. opened /login in a second tab): go where they meant to.
  useEffect(() => {
    if (status === "signedIn" && !sentTo) router.replace(nextPath);
  }, [status, sentTo, nextPath, router]);

  const fieldErrors = {
    email: touched && !emailLooksValid(email) ? "Enter a valid email address." : null,
    password:
      touched && mode === "signup" && !passwordIsValid(password)
        ? "Your password doesn't meet the requirements below."
        : touched && !password
          ? "Enter your password."
          : null,
    confirm: touched && mode === "signup" && confirm !== password ? "Passwords don't match." : null,
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    setError(null);
    setUnconfirmed(false);
    const valid =
      emailLooksValid(email) &&
      (mode === "login" ? password.length > 0 : passwordIsValid(password) && confirm === password);
    if (!valid) return;

    setSubmitting(true);
    try {
      const supabase = getSupabaseClient();
      if (mode === "login") {
        const { error: authError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (authError) {
          if (authError.code === "email_not_confirmed" || /not confirmed/i.test(authError.message)) {
            setUnconfirmed(true);
          }
          throw authError;
        }
        router.replace(nextPath);
        return;
      }

      const { data, error: authError } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: {
          emailRedirectTo: callbackUrl(nextPath),
          data: displayName.trim() ? { display_name: displayName.trim().slice(0, 60) } : undefined,
        },
      });
      if (authError) throw authError;
      if (data.session) {
        router.replace(nextPath);
      } else {
        // Email confirmation is on. Supabase answers the same way whether or
        // not the address is already registered, and so do we.
        setSentTo(email.trim());
      }
    } catch (caught) {
      setError(friendlyAuthError(caught));
    } finally {
      setSubmitting(false);
    }
  };

  if (sentTo) {
    return (
      <AuthShell title="Check your email" subtitle={`We sent a confirmation link to ${sentTo}.`}>
        <ol className={styles.steps}>
          <li>Open the email from Trekly and click the confirmation link.</li>
          <li>Use this same browser — the link signs you in here and brings you back.</li>
          <li>Not there after a few minutes? Check spam, or resend below.</li>
        </ol>
        <ResendConfirmation email={sentTo} next={nextPath} />
        <p className={styles.switch}>
          Wrong address?{" "}
          <button type="button" className={styles.linkButton} onClick={() => setSentTo(null)}>
            Start over
          </button>
        </p>
      </AuthShell>
    );
  }

  const checks = passwordChecks(password);

  return (
    <AuthShell
      title={mode === "login" ? "Welcome back" : "Create your account"}
      subtitle={
        mode === "login"
          ? "Sign in to see your gear, saved trails and profile."
          : "Save your gear and trails once, and find them on every device."
      }
    >
      {searchParams.get("expired") === "1" && mode === "login" && (
        <p className={ui.notice} role="status">
          Your session ended. Sign in again to pick up where you left off.
        </p>
      )}
      <GoogleButton next={nextPath} disabled={submitting || status === "unconfigured"} onError={setError} />
      <p className={styles.divider}>
        <span>or {mode === "login" ? "sign in" : "sign up"} with email</span>
      </p>
      <form className={styles.form} onSubmit={submit} noValidate>
        {mode === "signup" && (
          <label className={ui.field}>
            <span className={ui.label}>Name (optional)</span>
            <input
              className={ui.input}
              autoComplete="name"
              maxLength={60}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
            <span className={ui.hint}>Shown on your profile. You can change it later.</span>
          </label>
        )}

        <label className={ui.field}>
          <span className={ui.label}>Email</span>
          <input
            className={ui.input}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            aria-invalid={Boolean(fieldErrors.email)}
            aria-describedby={fieldErrors.email ? "email-error" : undefined}
          />
          {fieldErrors.email && (
            <span id="email-error" className={ui.fieldError}>
              {fieldErrors.email}
            </span>
          )}
        </label>

        <label className={ui.field}>
          <span className={styles.labelRow}>
            <span className={ui.label}>Password</span>
            {mode === "login" && (
              <Link href={`/forgot-password${carryNext}`} className={styles.inlineLink}>
                Forgot password?
              </Link>
            )}
          </span>
          <input
            className={ui.input}
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={Boolean(fieldErrors.password)}
            aria-describedby={mode === "signup" ? "password-rules" : fieldErrors.password ? "password-error" : undefined}
          />
          {fieldErrors.password && (
            <span id="password-error" className={ui.fieldError}>
              {fieldErrors.password}
            </span>
          )}
        </label>

        {mode === "signup" && (
          <>
            <ul id="password-rules" className={styles.rules} aria-label="Password requirements">
              {checks.map((check) => (
                <li key={check.label} className={check.met ? styles.ruleMet : undefined}>
                  <span aria-hidden="true">{check.met ? "✓" : "•"}</span> {check.label}
                  <span className={ui.srOnly}>{check.met ? " (met)" : " (not met)"}</span>
                </li>
              ))}
            </ul>
            <label className={ui.field}>
              <span className={ui.label}>Confirm password</span>
              <input
                className={ui.input}
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                aria-invalid={Boolean(fieldErrors.confirm)}
              />
              {fieldErrors.confirm && <span className={ui.fieldError}>{fieldErrors.confirm}</span>}
            </label>
          </>
        )}

        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
        {unconfirmed && <ResendConfirmation email={email.trim()} next={nextPath} />}

        <button className={`${ui.primary} ${styles.submit}`} type="submit" disabled={submitting || status === "unconfigured"}>
          {submitting ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        {status === "unconfigured" && (
          <p className={ui.error}>Sign-in isn&apos;t configured for this site yet.</p>
        )}
      </form>

      <p className={styles.switch}>
        {mode === "login" ? (
          <>
            New to Trekly? <Link href={`/signup${carryNext}`}>Create an account</Link>
          </>
        ) : (
          <>
            Already have an account? <Link href={`/login${carryNext}`}>Sign in</Link>
          </>
        )}
      </p>
    </AuthShell>
  );
}
