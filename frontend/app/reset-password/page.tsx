"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { AuthShell } from "@/components/AuthForm";
import ui from "@/components/ui.module.css";
import { friendlyAuthError, passwordChecks, passwordIsValid } from "@/lib/authLogic";
import { getSupabaseClient } from "@/lib/supabaseClient";

/**
 * Reached from a password-recovery email via /auth/callback, which signs the
 * user in with a recovery session. Without a session the link was invalid,
 * expired or opened elsewhere.
 */
export default function ResetPasswordPage() {
  const router = useRouter();
  const { status } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (status === "loading") {
    return <AuthShell title="Choose a new password" subtitle="Checking your reset link…" />;
  }

  if (status !== "signedIn" && !done) {
    return (
      <AuthShell title="This reset link isn't valid" subtitle="It may have expired, already been used, or been opened in a different browser.">
        <Link href="/forgot-password" className={ui.primary}>
          Send a new reset link
        </Link>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell title="Password updated" subtitle="You're signed in with your new password.">
        <button type="button" className={ui.primary} onClick={() => router.replace("/profile")}>
          Go to your profile
        </button>
      </AuthShell>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (!passwordIsValid(password) || confirm !== password) return;
    setSaving(true);
    setError(null);
    try {
      const { error: authError } = await getSupabaseClient().auth.updateUser({ password });
      if (authError) throw authError;
      setDone(true);
    } catch (caught) {
      setError(friendlyAuthError(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <AuthShell title="Choose a new password">
      <form onSubmit={submit} noValidate style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <label className={ui.field}>
          <span className={ui.label}>New password</span>
          <input
            className={ui.input}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={touched && !passwordIsValid(password)}
            aria-describedby="reset-rules"
          />
        </label>
        <ul id="reset-rules" className={ui.hint} aria-label="Password requirements">
          {passwordChecks(password).map((check) => (
            <li key={check.label}>
              {check.met ? "✓" : "•"} {check.label}
            </li>
          ))}
        </ul>
        <label className={ui.field}>
          <span className={ui.label}>Confirm new password</span>
          <input
            className={ui.input}
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            aria-invalid={touched && confirm !== password}
          />
          {touched && confirm !== password && <span className={ui.fieldError}>Passwords don&apos;t match.</span>}
        </label>
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
        <button type="submit" className={ui.primary} disabled={saving}>
          {saving ? "Saving…" : "Update password"}
        </button>
      </form>
    </AuthShell>
  );
}
