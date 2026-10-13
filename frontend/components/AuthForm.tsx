"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { safeNextPath } from "@/lib/auth";
import { getSupabaseClient } from "@/lib/supabaseClient";
import styles from "./AuthForm.module.css";

type Mode = "login" | "signup";

const COPY: Record<Mode, { title: string; subtitle: string; submit: string }> = {
  login: {
    title: "Welcome back",
    subtitle: "Log in to see your gear collection and saved plans.",
    submit: "Log in",
  },
  signup: {
    title: "Create your account",
    subtitle: "Save your gear once and reuse it every time you plan a trip.",
    submit: "Sign up",
  },
};

export default function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = safeNextPath(searchParams.get("next"));
  const nextQuery = searchParams.get("next")
    ? `?next=${encodeURIComponent(nextPath)}`
    : "";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmationSent, setConfirmationSent] = useState(false);

  const copy = COPY[mode];

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const supabase = getSupabaseClient();
      if (mode === "login") {
        const { error: authError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (authError) throw authError;
        router.push(nextPath);
        return;
      }

      const { data, error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${window.location.origin}${nextPath}`,
        },
      });
      if (authError) throw authError;
      if (data.session) {
        router.push(nextPath);
      } else {
        // Email confirmation is enabled: there's no session until they click the link.
        setConfirmationSent(true);
      }
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Something went wrong. Try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className={styles.page}>
      <div className={styles.card}>
        {confirmationSent ? (
          <>
            <h1 className={styles.title}>Check your email</h1>
            <p className={styles.subtitle}>
              We sent a confirmation link to <strong>{email}</strong>. Open it to
              finish creating your account.
            </p>
          </>
        ) : (
          <>
            <h1 className={styles.title}>{copy.title}</h1>
            <p className={styles.subtitle}>{copy.subtitle}</p>

            <form className={styles.form} onSubmit={handleSubmit}>
              <label className={styles.field}>
                <span className={styles.label}>Email</span>
                <input
                  className={styles.input}
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>

              <label className={styles.field}>
                <span className={styles.label}>Password</span>
                <input
                  className={styles.input}
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  minLength={mode === "signup" ? 8 : undefined}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                {mode === "signup" && (
                  <span className={styles.hint}>At least 8 characters.</span>
                )}
              </label>

              {error && (
                <p className={styles.error} role="alert">
                  {error}
                </p>
              )}

              <button className={styles.submit} type="submit" disabled={isSubmitting}>
                {isSubmitting ? "One moment…" : copy.submit}
              </button>
            </form>

            <p className={styles.switch}>
              {mode === "login" ? (
                <>
                  New to Trekly?{" "}
                  <Link href={`/signup${nextQuery}`}>Create an account</Link>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <Link href={`/login${nextQuery}`}>Log in</Link>
                </>
              )}
            </p>
          </>
        )}
      </div>
    </main>
  );
}
