"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { DELETE_CONFIRMATION, deleteAccount, updateProfile, type Profile } from "@/lib/accountApi";
import { emailLooksValid, friendlyAuthError, nextQuery, passwordChecks, passwordIsValid } from "@/lib/authLogic";
import { listOwnImages, removeImages, uploadImage, validateImage } from "@/lib/storage";
import { getSupabaseClient } from "@/lib/supabaseClient";
import { announceProfile } from "@/lib/useProfile";
import styles from "./page.module.css";

const BIO_LIMIT = 280;

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

function EditProfile({ profile }: { profile: Profile }) {
  const { user } = useAuth();
  const initial = {
    display_name: profile.display_name ?? "",
    username: profile.username ?? "",
    bio: profile.bio ?? "",
    home_region: profile.home_region ?? "",
  };
  const [values, setValues] = useState(initial);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!avatarFile) return;
    const url = URL.createObjectURL(avatarFile);
    queueMicrotask(() => setAvatarPreview(url));
    return () => URL.revokeObjectURL(url);
  }, [avatarFile]);

  const dirty =
    JSON.stringify(values) !== JSON.stringify(initial) || avatarFile !== null || removeAvatar;

  const set = (key: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setValues((current) => ({ ...current, [key]: event.target.value }));
    setStatus(null);
  };

  const reset = () => {
    setValues(initial);
    setAvatarFile(null);
    setAvatarPreview(null);
    setRemoveAvatar(false);
    setErrors({});
    setStatus(null);
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    const username = values.username.trim().toLowerCase();
    if (username && !/^[a-z0-9_]{3,30}$/.test(username)) {
      nextErrors.username = "Use 3–30 lowercase letters, numbers or underscores.";
    }
    if (values.bio.length > BIO_LIMIT) nextErrors.bio = `Keep your bio to ${BIO_LIMIT} characters.`;
    if (avatarFile) {
      const problem = validateImage(avatarFile, "avatars");
      if (problem) nextErrors.avatar = problem;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length || !user) return;

    setSaving(true);
    setStatus(null);
    let uploaded: string | null = null;
    try {
      const update: Record<string, string | null> = {
        display_name: values.display_name.trim() || null,
        username: username || null,
        bio: values.bio.trim() || null,
        home_region: values.home_region.trim() || null,
      };
      if (avatarFile) {
        uploaded = await uploadImage("avatars", user.id, avatarFile);
        update.avatar_path = uploaded;
      } else if (removeAvatar) {
        update.avatar_path = null;
      }
      const saved = await updateProfile(update);
      if (profile.avatar_path && profile.avatar_path !== saved.avatar_path) {
        removeImages("avatars", [profile.avatar_path]).catch(() => undefined);
      }
      announceProfile(saved);
      setAvatarFile(null);
      setAvatarPreview(null);
      setRemoveAvatar(false);
      setStatus({ ok: true, message: "Profile saved." });
    } catch (caught) {
      if (uploaded) removeImages("avatars", [uploaded]).catch(() => undefined);
      if (caught instanceof ApiError && caught.status === 409) {
        setErrors({ username: caught.message });
      } else {
        setStatus({ ok: false, message: caught instanceof Error ? caught.message : "That didn't save." });
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={save} noValidate>
      <div className={styles.avatarRow}>
        <Avatar
          path={removeAvatar ? null : profile.avatar_path}
          preview={avatarPreview}
          name={values.display_name || profile.display_name}
          email={profile.email}
          size={72}
        />
        <div className={ui.field}>
          <label className={ui.label} htmlFor="avatar-input">
            Profile photo
          </label>
          <input
            id="avatar-input"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => {
              setAvatarFile(event.target.files?.[0] ?? null);
              setRemoveAvatar(false);
            }}
          />
          <span className={ui.hint}>JPEG, PNG or WebP up to 2 MB.</span>
          {profile.avatar_path && !avatarFile && (
            <label className={styles.checkbox}>
              <input type="checkbox" checked={removeAvatar} onChange={(event) => setRemoveAvatar(event.target.checked)} />
              Remove photo and use initials
            </label>
          )}
          {errors.avatar && <span className={ui.fieldError}>{errors.avatar}</span>}
        </div>
      </div>

      <div className={ui.row}>
        <label className={ui.field}>
          <span className={ui.label}>Display name</span>
          <input className={ui.input} value={values.display_name} onChange={set("display_name")} maxLength={60} autoComplete="name" />
        </label>
        <label className={ui.field}>
          <span className={ui.label}>Username</span>
          <input
            className={ui.input}
            value={values.username}
            onChange={set("username")}
            maxLength={30}
            autoCapitalize="none"
            spellCheck={false}
            aria-invalid={Boolean(errors.username)}
            aria-describedby="username-hint"
          />
          <span id="username-hint" className={ui.hint}>
            Unique · lowercase letters, numbers and underscores
          </span>
          {errors.username && <span className={ui.fieldError}>{errors.username}</span>}
        </label>
      </div>

      <label className={ui.field}>
        <span className={styles.labelRow}>
          <span className={ui.label}>Bio</span>
          <span className={values.bio.length > BIO_LIMIT ? ui.fieldError : ui.hint} aria-live="polite">
            {values.bio.length}/{BIO_LIMIT}
          </span>
        </span>
        <textarea className={ui.input} rows={3} value={values.bio} onChange={set("bio")} aria-invalid={Boolean(errors.bio)} />
        {errors.bio && <span className={ui.fieldError}>{errors.bio}</span>}
      </label>

      <label className={ui.field}>
        <span className={ui.label}>Home region (optional)</span>
        <input className={ui.input} value={values.home_region} onChange={set("home_region")} maxLength={80} placeholder="e.g. Pacific Northwest" />
      </label>

      {status && (
        <p className={status.ok ? ui.success : ui.error} role={status.ok ? "status" : "alert"}>
          {status.message}
        </p>
      )}
      <div className={styles.formActions}>
        <button type="button" className={ui.ghost} onClick={reset} disabled={!dirty || saving}>
          Cancel
        </button>
        <button type="submit" className={ui.primary} disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save profile"}
        </button>
      </div>
    </form>
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
      for (const bucket of ["gear-photos", "avatars"] as const) {
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
        This permanently deletes your account, profile, photos, saved trails and gear inventory. It can&apos;t
        be undone. Shared catalogue products aren&apos;t affected.
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
      <Card id="edit-profile" title="Profile" description="How you appear in Trekly.">
        <EditProfile profile={profile} />
      </Card>
      <Card id="privacy" title="Privacy">
        <p>
          Your profile is <strong>private</strong>. Trekly doesn&apos;t have public profiles, so your name, bio,
          gear and saved trails are only visible to you when you&apos;re signed in. Your email is never shown to
          anyone else.
        </p>
      </Card>
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
