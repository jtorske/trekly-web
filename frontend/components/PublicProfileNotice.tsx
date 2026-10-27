"use client";

import { useEffect, useState, type FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { updateProfile } from "@/lib/accountApi";
import { getPrivacy, updatePrivacy } from "@/lib/profilesApi";
import { announceProfile, useProfile } from "@/lib/useProfile";
import ui from "./ui.module.css";
import styles from "./PublicProfileNotice.module.css";

const USERNAME = /^[a-z0-9_]{3,30}$/;
// "Later" on the username prompt lasts for this browser session only.
const LATER_KEY = "trekly:username-prompt-later";

function laterChosen(): boolean {
  try {
    return sessionStorage.getItem(LATER_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Two one-off prompts for signed-in users, shown in a corner card:
 *
 * - No username yet: pick one (a public profile needs it for its address).
 * - Accounts from before public profiles: they stay private, and this
 *   explains that profiles can now be public, once, until dismissed.
 */
export default function PublicProfileNotice() {
  const router = useRouter();
  const pathname = usePathname();
  const { profile } = useProfile();
  const [noticePending, setNoticePending] = useState(false);
  // Nothing renders until the profile has loaded on the client, so reading
  // sessionStorage here can't cause a hydration mismatch.
  const [later, setLater] = useState(() => typeof window !== "undefined" && laterChosen());
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const needsUsername = Boolean(profile) && !profile?.username;

  useEffect(() => {
    if (!profile?.username) return;
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then((settings) => setNoticePending(settings.public_notice_pending))
      .catch(() => undefined);
    return () => controller.abort();
  }, [profile?.username]);

  if (!profile || pathname.startsWith("/auth")) return null;

  if (needsUsername) {
    if (later) return null;
    const submit = async (event: FormEvent) => {
      event.preventDefault();
      const value = username.trim().toLowerCase();
      if (!USERNAME.test(value)) {
        setError("Use 3–30 lowercase letters, numbers or underscores.");
        return;
      }
      setSaving(true);
      setError(null);
      try {
        announceProfile(await updateProfile({ username: value }));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "That didn't save. Try again.");
      } finally {
        setSaving(false);
      }
    };
    return (
      <aside className={styles.card} aria-labelledby="username-prompt-title">
        <h2 id="username-prompt-title" className={styles.title}>
          Choose your username
        </h2>
        <p className={styles.text}>It&apos;s your profile&apos;s address on Trekly, like /u/your_name.</p>
        <form className={styles.form} onSubmit={submit} noValidate>
          <label className={ui.srOnly} htmlFor="username-prompt">
            Username
          </label>
          <span className={styles.inputWrap}>
            <span className={styles.at} aria-hidden="true">
              @
            </span>
            <input
              id="username-prompt"
              className={`${ui.input} ${styles.input}`}
              value={username}
              onChange={(event) => setUsername(event.target.value.toLowerCase())}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={30}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "username-prompt-error" : undefined}
            />
          </span>
          <button type="submit" className={ui.primary} disabled={saving || !username}>
            {saving ? "Saving…" : "Save"}
          </button>
        </form>
        {error && (
          <p id="username-prompt-error" className={ui.fieldError} role="alert">
            {error}
          </p>
        )}
        <button
          type="button"
          className={`${ui.ghost} ${styles.dismiss}`}
          onClick={() => {
            try {
              sessionStorage.setItem(LATER_KEY, "1");
            } catch {
              // Private mode: it just comes back on the next page.
            }
            setLater(true);
          }}
        >
          Later
        </button>
      </aside>
    );
  }

  if (!noticePending) return null;
  const dismiss = () => {
    setNoticePending(false);
    updatePrivacy({ public_notice_pending: false }).catch(() => undefined);
  };
  return (
    <aside className={styles.card} aria-labelledby="public-notice-title">
      <h2 id="public-notice-title" className={styles.title}>
        Profiles can now be public
      </h2>
      <p className={styles.text}>
        Trekly profiles can be shared at a public address, showing only the sections you pick. Yours is still private,
        and stays that way until you change it.
      </p>
      <div className={styles.actions}>
        <button
          type="button"
          className={ui.primary}
          onClick={() => {
            dismiss();
            router.push("/profile?tab=settings#privacy");
          }}
        >
          Review privacy settings
        </button>
        <button type="button" className={ui.ghost} onClick={dismiss}>
          Dismiss
        </button>
      </div>
    </aside>
  );
}
