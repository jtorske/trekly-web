"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { AuthShell } from "@/components/AuthForm";
import ui from "@/components/ui.module.css";
import { emailLooksValid, friendlyAuthError, nextQuery } from "@/lib/authLogic";
import { getSupabaseClient } from "@/lib/supabaseClient";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [touched, setTouched] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (!emailLooksValid(email)) return;
    setSending(true);
    setError(null);
    try {
      const { error: authError } = await getSupabaseClient().auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/auth/callback${nextQuery("/reset-password")}`,
      });
      // Rate limits and network errors are worth showing; nothing else is,
      // so the page never reveals whether an account exists.
      if (authError && /rate limit|fetch|network/i.test(authError.message)) throw authError;
      setSent(true);
    } catch (caught) {
      setError(friendlyAuthError(caught));
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    return (
      <AuthShell title="Check your email" subtitle={`If an account exists for ${email.trim()}, a reset link is on its way.`}>
        <p>Open the link in this browser to choose a new password. It expires after a while and works once.</p>
        <Link href="/login" className={ui.secondary}>
          Back to sign in
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Reset your password" subtitle="Enter your email and we'll send you a link to choose a new one.">
      <form onSubmit={submit} noValidate style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <label className={ui.field}>
          <span className={ui.label}>Email</span>
          <input
            className={ui.input}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            aria-invalid={touched && !emailLooksValid(email)}
          />
          {touched && !emailLooksValid(email) && <span className={ui.fieldError}>Enter a valid email address.</span>}
        </label>
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
        <button type="submit" className={ui.primary} disabled={sending}>
          {sending ? "Sending…" : "Send reset link"}
        </button>
      </form>
      <p style={{ textAlign: "center", fontSize: "0.9rem" }}>
        Remembered it? <Link href="/login" style={{ color: "var(--color-rust)", fontWeight: 600 }}>Sign in</Link>
      </p>
    </AuthShell>
  );
}
