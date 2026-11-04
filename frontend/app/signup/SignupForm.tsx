"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, MailCheck } from "lucide-react";
import { GoogleButton, ResendConfirmation, callbackUrl } from "@/components/AuthForm";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import { emailLooksValid, friendlyAuthError, nextQuery, passwordChecks, passwordIsValid, safeNextPath } from "@/lib/authLogic";
import { getSupabaseClient } from "@/lib/supabaseClient";
import styles from "./signup.module.css";

const PHOTO = { src: "/images/IMG_8988.jpeg", position: "center 55%" };

/**
 * Step 0 of joining: just an account, by Google or email and password. Name,
 * username and the rest come right after, on /welcome (the app sends every
 * new account there on its first sign-in).
 */
export default function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status } = useAuth();
  const nextPath = safeNextPath(searchParams.get("next"));
  const carryNext = searchParams.get("next") ? nextQuery(nextPath) : "";
  const emailId = useId();
  const passwordId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  // Already signed in (a second tab): the app takes it from there.
  useEffect(() => {
    if (status === "signedIn" && !sentTo) router.replace(nextPath);
  }, [status, sentTo, nextPath, router]);

  const emailError = touched && !emailLooksValid(email) ? "Enter a valid email address." : null;
  const passwordError = touched && !passwordIsValid(password) ? "Your password doesn't meet the requirements below." : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    setError(null);
    if (!emailLooksValid(email) || !passwordIsValid(password)) return;
    setSubmitting(true);
    try {
      const { data, error: authError } = await getSupabaseClient().auth.signUp({
        email: email.trim(),
        password,
        options: { emailRedirectTo: callbackUrl(nextPath) },
      });
      if (authError) throw authError;
      // With confirmation off there's a session at once; the app sends them to /welcome.
      if (data.session) router.replace(nextPath);
      // Supabase answers the same way whether or not the address is already
      // registered, and so do we.
      else setSentTo(email.trim());
    } catch (caught) {
      setError(friendlyAuthError(caught));
    } finally {
      setSubmitting(false);
    }
  };

  if (sentTo) {
    return (
      <main className={styles.inbox}>
        <span className={styles.inboxLogo} role="img" aria-label="Trekly" />
        <div className={styles.inboxCard}>
          <span className={styles.inboxIcon} aria-hidden="true">
            <MailCheck size={36} />
          </span>
          <h1 className={styles.heading}>Check your inbox</h1>
          <p className={styles.lead}>
            We sent a link to <strong>{sentTo}</strong>. Click it to confirm your email, and we&apos;ll get your account set up.
          </p>
          <ul className={styles.tips}>
            <li>Open it in this browser: the link signs you in here.</li>
            <li>Nothing after a few minutes? Check your spam folder, or send it again.</li>
          </ul>
          <ResendConfirmation email={sentTo} next={nextPath} />
          <p className={styles.switch}>
            Wrong address?{" "}
            <button type="button" className={styles.linkButton} onClick={() => setSentTo(null)}>
              Start over
            </button>
          </p>
        </div>
      </main>
    );
  }

  const checks = passwordChecks(password);

  return (
    <div className={styles.page}>
      <div className={styles.visual} aria-hidden="true">
        <Image
          src={PHOTO.src}
          alt=""
          fill
          priority
          sizes="(max-width: 899px) 100vw, 50vw"
          className={styles.photo}
          style={{ objectPosition: PHOTO.position }}
        />
        <div className={styles.shade} />
        <p className={styles.tagline}>Every great trip starts with a plan.</p>
      </div>
      <Link href="/landing" className={styles.logoLink} aria-label="Trekly home">
        <span className={styles.logo} />
      </Link>

      <main className={styles.panel}>
        <div className={styles.formWrap}>
          <h1 className={styles.heading}>Create your account</h1>
          <p className={styles.lead}>Save trails, plan trips and keep your gear in one place, on every device.</p>

          <GoogleButton
            next={nextPath}
            disabled={submitting || status === "unconfigured"}
            onError={setError}
            className={styles.google}
          />
          <p className={styles.divider}>
            <span>or with email</span>
          </p>

          <form className={styles.form} onSubmit={submit} noValidate>
            <label className={ui.field} htmlFor={emailId}>
              <span className={ui.label}>Email</span>
              <input
                id={emailId}
                className={`${ui.input} ${styles.input}`}
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(emailError)}
                aria-describedby={emailError ? `${emailId}-error` : undefined}
              />
              {emailError && (
                <span id={`${emailId}-error`} className={ui.fieldError}>
                  {emailError}
                </span>
              )}
            </label>

            <div className={ui.field}>
              <label className={ui.label} htmlFor={passwordId}>
                Password
              </label>
              <span className={styles.passwordWrap}>
                <input
                  id={passwordId}
                  className={`${ui.input} ${styles.input}`}
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-invalid={Boolean(passwordError)}
                  aria-describedby={`${passwordId}-rules${passwordError ? ` ${passwordId}-error` : ""}`}
                />
                <button
                  type="button"
                  className={styles.reveal}
                  onClick={() => setShowPassword((shown) => !shown)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
                </button>
              </span>
              {passwordError && (
                <span id={`${passwordId}-error`} className={ui.fieldError}>
                  {passwordError}
                </span>
              )}
              <ul id={`${passwordId}-rules`} className={styles.rules} aria-label="Password requirements">
                {checks.map((check) => (
                  <li key={check.label} className={check.met ? styles.ruleMet : undefined}>
                    <span aria-hidden="true">{check.met ? "✓" : "•"}</span> {check.label}
                    <span className={ui.srOnly}>{check.met ? " (met)" : " (not met)"}</span>
                  </li>
                ))}
              </ul>
            </div>

            {error && (
              <p className={ui.error} role="alert">
                {error}
              </p>
            )}

            <button className={styles.submit} type="submit" disabled={submitting || status === "unconfigured"}>
              {submitting ? "One moment…" : "Create account"}
            </button>
            {status === "unconfigured" && <p className={ui.error}>Sign-in isn&apos;t configured for this site yet.</p>}
          </form>

          <p className={styles.legal}>
            By creating an account you agree to the <Link href="/terms">Terms</Link> and{" "}
            <Link href="/privacy">Privacy Policy</Link>.
          </p>
          <p className={styles.switch}>
            Already have an account? <Link href={`/login${carryNext}`}>Sign in</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
