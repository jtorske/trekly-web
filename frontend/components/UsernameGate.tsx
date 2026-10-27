"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { AuthShell } from "@/components/AuthForm";
import UsernameField, { useUsernameStatus } from "@/components/UsernameField";
import ui from "@/components/ui.module.css";
import { updateProfile, type Profile } from "@/lib/accountApi";
import { getPrivacy } from "@/lib/profilesApi";
import { announceProfile, useProfile } from "@/lib/useProfile";
import { normalizeUsername, suggestionHint, usernameGate, usernameReady } from "@/lib/usernames";
import styles from "./AuthForm.module.css";

// Per browser and account: "this user has a username", so returning users
// never wait on the profile request before seeing the page.
const knownKey = (userId: string) => `trekly:has-username:${userId}`;

function knownToHaveUsername(userId: string | undefined): boolean {
  if (!userId) return false;
  try {
    return localStorage.getItem(knownKey(userId)) === "1";
  } catch {
    return false;
  }
}

/**
 * Every account needs a username. A signed-in user without one (new from
 * Google, or from before usernames were required) gets this step instead of
 * any app page until they choose; they can still sign out. Choosing one
 * doesn't change any privacy setting.
 */
export default function UsernameGate({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const pathname = usePathname();
  const { profile, loading, error } = useProfile();

  useEffect(() => {
    if (!profile?.username) return;
    try {
      localStorage.setItem(knownKey(profile.id), "1");
    } catch {
      // Storage unavailable: the next visit just waits for the profile.
    }
  }, [profile?.id, profile?.username]);

  const gate = usernameGate({
    authStatus: status,
    pathname,
    profileLoading: loading,
    profileError: error,
    username: profile?.username,
    knownToHaveUsername: status === "signedIn" && knownToHaveUsername(user?.id),
  });

  if (gate === "wait") {
    return (
      <AuthShell title="One moment…">
        <p className={ui.hint} role="status">
          Loading your account.
        </p>
      </AuthShell>
    );
  }
  if (gate === "choose" && profile) return <ChooseUsername profile={profile} email={user?.email ?? null} />;
  return <>{children}</>;
}

function ChooseUsername({ profile, email }: { profile: Profile; email: string | null }) {
  const { signOut } = useAuth();
  const [username, setUsername] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPrivate, setIsPrivate] = useState<boolean | null>(null);
  const status = useUsernameStatus(username);

  useEffect(() => {
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then((settings) => setIsPrivate(settings.is_private))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (!usernameReady(status)) return;
    setSaving(true);
    try {
      announceProfile(await updateProfile({ username: normalizeUsername(username) }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't save. Try again.");
      setSaving(false);
    }
  };

  return (
    <AuthShell
      title="Choose your username"
      subtitle="Every Trekly account has one. It's your profile's address, like /u/your_name, and you can change it later."
    >
      <form className={styles.form} onSubmit={submit} noValidate>
        <UsernameField
          id="choose-username"
          value={username}
          onChange={setUsername}
          status={status}
          suggestFrom={suggestionHint(profile.display_name, email)}
          showError={submitted}
          autoFocus
        />
        {isPrivate !== null && (
          <p className={ui.hint}>
            Choosing a username doesn&apos;t change your privacy settings.{" "}
            {isPrivate
              ? "Your profile is private and stays that way."
              : "Trekly profiles are public by default, showing only the sections you pick; you can hide sections or make yours private in Settings → Privacy."}{" "}
            See the{" "}
            <Link href="/privacy" className={styles.inlineLink}>
              Privacy Policy
            </Link>
            .
          </p>
        )}
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
        <button
          className={`${ui.primary} ${styles.submit}`}
          type="submit"
          disabled={saving || status.state === "checking"}
        >
          {saving ? "Saving…" : "Continue"}
        </button>
      </form>
      <p className={styles.switch}>
        Not you?{" "}
        <button type="button" className={styles.linkButton} onClick={() => signOut("/")}>
          Sign out
        </button>
      </p>
    </AuthShell>
  );
}
