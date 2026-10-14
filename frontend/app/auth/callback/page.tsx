"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthShell } from "@/components/AuthForm";
import ui from "@/components/ui.module.css";
import { authRedirectError, nextQuery, safeNextPath } from "@/lib/authLogic";
import { getSupabaseClient } from "@/lib/supabaseClient";

/**
 * Landing page for Supabase email links (signup confirmation, password
 * recovery, email change). The Supabase client exchanges the PKCE `code` in
 * the URL for a session during initialisation; we wait for that, then send
 * the user on to `next`.
 */
function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNextPath(searchParams.get("next"));
  const isRecovery = next.startsWith("/reset-password");
  const [problem, setProblem] = useState<"link" | "browser" | "signin" | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const redirectError = authRedirectError(window.location.search, window.location.hash);
    if (redirectError) {
      queueMicrotask(() => {
        setProblem("link");
        setMessage(redirectError);
      });
      return;
    }
    let cancelled = false;
    getSupabaseClient()
      .auth.getSession()
      .then(({ data, error }) => {
        if (cancelled) return;
        if (data.session) {
          router.replace(next);
          return;
        }
        // The code could not be exchanged — typically the link was opened in
        // a different browser than the one that requested it. A signup link
        // still confirms the address before redirecting here.
        setProblem(error ? "link" : searchParams.get("code") ? "browser" : "signin");
        setMessage(error ? error.message : null);
      })
      .catch(() => {
        if (!cancelled) setProblem("link");
      });
    return () => {
      cancelled = true;
    };
  }, [next, router, searchParams]);

  if (!problem) {
    return (
      <AuthShell title="Signing you in…" subtitle="One moment while we confirm your link.">
        <p className={ui.hint} role="status">
          If nothing happens, <Link href="/login">sign in here</Link>.
        </p>
      </AuthShell>
    );
  }

  if (problem === "link") {
    return (
      <AuthShell title="That link didn't work" subtitle={message ?? "This link is invalid or has expired."}>
        <p>Links can only be used once and expire after a while.</p>
        {isRecovery ? (
          <Link href="/forgot-password" className={ui.primary}>
            Send a new reset link
          </Link>
        ) : (
          <Link href={`/login${nextQuery(next)}`} className={ui.primary}>
            Sign in or resend confirmation
          </Link>
        )}
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={isRecovery ? "Open the link in the same browser" : "Your email is confirmed"}
      subtitle={
        isRecovery
          ? "For security, password reset links only work in the browser where you requested them."
          : "Sign in to continue — this browser didn't start the signup, so we can't sign you in automatically."
      }
    >
      {isRecovery ? (
        <Link href="/forgot-password" className={ui.primary}>
          Request a new reset link here
        </Link>
      ) : (
        <Link href={`/login${nextQuery(next)}`} className={ui.primary}>
          Sign in
        </Link>
      )}
    </AuthShell>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense>
      <CallbackContent />
    </Suspense>
  );
}
