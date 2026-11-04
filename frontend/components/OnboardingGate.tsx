"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { AuthShell } from "@/components/AuthForm";
import ui from "@/components/ui.module.css";
import { onboardingGate, welcomeHref } from "@/lib/onboarding";
import { useProfile } from "@/lib/useProfile";

// Per browser and account: "this user has finished setup", so returning
// users never wait on the profile request before seeing the page.
const knownKey = (userId: string) => `trekly:set-up:${userId}`;

function knownSetUp(userId: string | undefined): boolean {
  if (!userId) return false;
  try {
    return localStorage.getItem(knownKey(userId)) === "1";
  } catch {
    return false;
  }
}

/**
 * Sends a signed-in user who hasn't finished setup to /welcome before any
 * app page: always without a username (the one required step), and once
 * for everyone else until they finish or skip it. They come back to the
 * page they asked for afterwards.
 */
export default function OnboardingGate({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const { profile, loading, error } = useProfile();
  const setUp = Boolean(profile?.username) && profile?.onboarding_pending === false;

  useEffect(() => {
    if (!profile) return;
    try {
      if (setUp) localStorage.setItem(knownKey(profile.id), "1");
      else localStorage.removeItem(knownKey(profile.id));
    } catch {
      // Storage unavailable: the next visit just waits for the profile.
    }
  }, [profile, setUp]);

  const gate = onboardingGate({
    authStatus: status,
    pathname,
    profileLoading: loading,
    profileError: error,
    username: profile?.username,
    onboardingPending: profile?.onboarding_pending,
    knownSetUp: status === "signedIn" && knownSetUp(user?.id),
  });

  useEffect(() => {
    if (gate !== "welcome") return;
    router.replace(welcomeHref(`${window.location.pathname}${window.location.search}`));
  }, [gate, router]);

  if (gate === "pass") return <>{children}</>;
  return (
    <AuthShell title="One moment…">
      <p className={ui.hint} role="status">
        {gate === "wait" ? "Loading your account." : "Taking you to set up your account."}
      </p>
    </AuthShell>
  );
}
