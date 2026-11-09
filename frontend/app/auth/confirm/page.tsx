"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthForm";
import ui from "@/components/ui.module.css";
import { friendlyAuthError } from "@/lib/authLogic";
import { confirmDestination, confirmProblem, parseConfirmLink, type ConfirmLink, type LinkProblem } from "@/lib/emailLinks";
import { getSupabaseClient } from "@/lib/supabaseClient";
import { toast } from "@/lib/toast";

type Outcome = { kind: "done" } | { kind: "halfway" } | { kind: "problem"; problem: LinkProblem; detail?: string };

// A token works once. React's dev double-run of effects (and any re-render)
// must not spend it twice, so each token hash is verified at most once.
const attempts = new Map<string, Promise<Outcome>>();

async function verify(link: ConfirmLink): Promise<Outcome> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.auth.verifyOtp({ token_hash: link.tokenHash, type: link.type });
  if (error) {
    const { data: current } = await supabase.auth.getSession();
    const expired = error.code === "otp_expired" || /expired|invalid/i.test(error.message);
    return {
      kind: "problem",
      problem: confirmProblem(link.type, Boolean(current.session)),
      detail: expired ? undefined : friendlyAuthError(error),
    };
  }
  // With "confirm on both addresses" on, the first of the two email-change
  // links is accepted without a session: the other address still has to confirm.
  if (link.type === "email_change" && !data.session) return { kind: "halfway" };
  return { kind: "done" };
}

/**
 * Landing page for every link in Trekly's auth emails (sign-up, password
 * reset, email change, magic link, invite). The link carries a token hash
 * rather than a PKCE code, so it works in any browser, not only the one that
 * asked for the email.
 */
export default function AuthConfirmPage() {
  const router = useRouter();
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => {
    const link = parseConfirmLink(window.location.search);
    if (!link) {
      queueMicrotask(() => setOutcome({ kind: "problem", problem: confirmProblem(null, false) }));
      return;
    }
    let attempt = attempts.get(link.tokenHash);
    if (!attempt) {
      attempt = verify(link).catch(
        (): Outcome => ({
          kind: "problem",
          problem: confirmProblem(link.type, false),
          detail: "We couldn't reach the sign-in service. Check your connection and open the link again.",
        }),
      );
      attempts.set(link.tokenHash, attempt);
    }
    let cancelled = false;
    void attempt.then((result) => {
      if (cancelled) return;
      if (result.kind === "done") {
        if (link.type === "email_change") toast.success("Your email address is updated");
        router.replace(confirmDestination(link.type));
        return;
      }
      setOutcome(result);
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!outcome || outcome.kind === "done") {
    return (
      <AuthShell title="Checking your link…" subtitle="One moment.">
        <p className={ui.hint} role="status">
          If nothing happens, <Link href="/login">sign in here</Link>.
        </p>
      </AuthShell>
    );
  }

  if (outcome.kind === "halfway") {
    return (
      <AuthShell
        title="One more step"
        subtitle="That address is confirmed. We also sent a link to your other address: open it to finish changing your email."
      >
        <Link href="/settings/email-and-password" className={ui.primary}>
          Back to settings
        </Link>
      </AuthShell>
    );
  }

  const { problem, detail } = outcome;
  return (
    <AuthShell title={problem.title} subtitle={problem.subtitle}>
      {detail ? <p className={ui.hint}>{detail}</p> : null}
      <Link href={problem.action.href} className={ui.primary}>
        {problem.action.label}
      </Link>
    </AuthShell>
  );
}
