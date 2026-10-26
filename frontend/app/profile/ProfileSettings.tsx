"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import ui from "@/components/ui.module.css";
import { DELETE_CONFIRMATION, deleteAccount, type Profile } from "@/lib/accountApi";
import { emailLooksValid, friendlyAuthError, nextQuery, passwordChecks, passwordIsValid } from "@/lib/authLogic";
import { listOwnImages, removeImages } from "@/lib/storage";
import { getSupabaseClient } from "@/lib/supabaseClient";
import styles from "./page.module.css";

function Card({ id, title, description, children }: { id: string; title: string; description?: string; children: React.ReactNode }) {
  return (
    <section id={id} className={styles.card} aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className={styles.cardTitle}>
        {title}
      </h2>
      {description && <p className={styles.cardDescription}>{description}</p>}
      {children}
    </section>
  );
}

function ChangeEmail({ email }: { email: string | null }) {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!emailLooksValid(value)) {
      setStatus({ ok: false, message: "Enter a valid email address." });
      return;
    }
    if (email && value.trim().toLowerCase() === email.toLowerCase()) {
      setStatus({ ok: false, message: "That's already your email." });
      return;
    }
    setSaving(true);
    setStatus(null);
    try {
      const { error } = await getSupabaseClient().auth.updateUser(
        { email: value.trim() },
        { emailRedirectTo: `${window.location.origin}/auth/callback${nextQuery("/profile?tab=settings")}` },
      );
      if (error) throw error;
      setStatus({
        ok: true,
        message: `Check both ${email ?? "your current address"} and ${value.trim()} — confirm the change from the links we sent.`,
      });
      setValue("");
    } catch (caught) {
      setStatus({ ok: false, message: friendlyAuthError(caught) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={submit} noValidate>
      <p className={ui.hint}>
        Signed in as <strong>{email ?? "—"}</strong>
      </p>
      <label className={ui.field}>
        <span className={ui.label}>New email</span>
        <input className={ui.input} type="email" autoComplete="email" value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      {status && (
        <p className={status.ok ? ui.success : ui.error} role={status.ok ? "status" : "alert"}>
          {status.message}
        </p>
      )}
      <div className={styles.formActions}>
        <button type="submit" className={ui.secondary} disabled={saving || !value}>
          {saving ? "Sending…" : "Change email"}
        </button>
      </div>
    </form>
  );
}

function ChangePassword() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [nonce, setNonce] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!passwordIsValid(password)) {
      setStatus({ ok: false, message: "Your new password doesn't meet the requirements." });
      return;
    }
    if (password !== confirm) {
      setStatus({ ok: false, message: "Passwords don't match." });
      return;
    }
    setSaving(true);
    setStatus(null);
    const supabase = getSupabaseClient();
    try {
      const { error } = await supabase.auth.updateUser(needsCode ? { password, nonce: nonce.trim() } : { password });
      if (error) {
        if (error.code === "reauthentication_needed" || /reauthentication/i.test(error.message)) {
          // Secure password change is on: confirm it's really them with an emailed code.
          const { error: reauthError } = await supabase.auth.reauthenticate();
          if (reauthError) throw reauthError;
          setNeedsCode(true);
          setStatus({ ok: true, message: "For security we emailed you a code. Enter it below to finish." });
          return;
        }
        throw error;
      }
      setPassword("");
      setConfirm("");
      setNonce("");
      setNeedsCode(false);
      setStatus({ ok: true, message: "Password updated." });
    } catch (caught) {
      setStatus({ ok: false, message: friendlyAuthError(caught) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={submit} noValidate>
      <div className={ui.row}>
        <label className={ui.field}>
          <span className={ui.label}>New password</span>
          <input className={ui.input} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className={ui.field}>
          <span className={ui.label}>Confirm new password</span>
          <input className={ui.input} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </label>
      </div>
      <ul className={ui.hint} aria-label="Password requirements">
        {passwordChecks(password).map((check) => (
          <li key={check.label}>
            {check.met ? "✓" : "•"} {check.label}
          </li>
        ))}
      </ul>
      {needsCode && (
        <label className={ui.field}>
          <span className={ui.label}>Code from your email</span>
          <input className={ui.input} inputMode="numeric" autoComplete="one-time-code" value={nonce} onChange={(e) => setNonce(e.target.value)} />
        </label>
      )}
      {status && (
        <p className={status.ok ? ui.success : ui.error} role={status.ok ? "status" : "alert"}>
          {status.message}
        </p>
      )}
      <div className={styles.formActions}>
        <Link href="/forgot-password" className={ui.ghost}>
          Forgot your password?
        </Link>
        <button type="submit" className={ui.secondary} disabled={saving || !password}>
          {saving ? "Saving…" : needsCode ? "Confirm and update" : "Update password"}
        </button>
      </div>
    </form>
  );
}

function SignOut() {
  const { signOut } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setBusy(true);
    await signOut("/landing");
  };

  return confirming ? (
    <div className={styles.confirmRow} role="alertdialog" aria-label="Confirm sign out">
      <span>Sign out of Trekly on this device?</span>
      <button type="button" className={ui.secondary} onClick={() => setConfirming(false)} disabled={busy}>
        Stay signed in
      </button>
      <button type="button" className={ui.primary} onClick={go} disabled={busy}>
        {busy ? "Signing out…" : "Sign out"}
      </button>
    </div>
  ) : (
    <button type="button" className={ui.secondary} onClick={() => setConfirming(true)}>
      Sign out
    </button>
  );
}

function DeleteAccount() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matches = typed.trim().toLowerCase() === DELETE_CONFIRMATION;

  const remove = async () => {
    if (!user || !matches) return;
    setBusy(true);
    setError(null);
    try {
      // Photos live in Storage, which the database can't clean up itself.
      for (const bucket of ["gear-photos", "avatars", "hike-photos"] as const) {
        const paths = await listOwnImages(bucket, user.id);
        await removeImages(bucket, paths);
      }
      await deleteAccount(typed);
      await signOut("/landing?account=deleted");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We couldn't delete your account. Nothing was removed from it.");
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className={ui.danger} onClick={() => setOpen(true)}>
        Delete account…
      </button>
    );
  }
  return (
    <div className={styles.form}>
      <p>
        This permanently deletes your account, profile, photos, saved trails, gear inventory and setups, trip
        plans and campsite alerts. It can&apos;t be undone. Shared catalogue products aren&apos;t affected.
      </p>
      <label className={ui.field}>
        <span className={ui.label}>
          Type <strong>{DELETE_CONFIRMATION}</strong> to confirm
        </span>
        <input className={ui.input} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
      </label>
      {error && (
        <p className={ui.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.formActions}>
        <button type="button" className={ui.ghost} onClick={() => setOpen(false)} disabled={busy}>
          Cancel
        </button>
        <button type="button" className={ui.danger} onClick={remove} disabled={!matches || busy}>
          {busy ? "Deleting…" : "Permanently delete my account"}
        </button>
      </div>
    </div>
  );
}

export default function ProfileSettings({ profile }: { profile: Profile }) {
  return (
    <div className={styles.settings}>
      <Card id="email" title="Email">
        <ChangeEmail email={profile.email} />
      </Card>
      <Card id="password" title="Password">
        <ChangePassword />
      </Card>
      <Card id="session" title="Sign out" description="Ends your session in this browser. Your data stays saved to your account.">
        <SignOut />
      </Card>
      <Card id="delete" title="Delete account">
        <DeleteAccount />
      </Card>
    </div>
  );
}
