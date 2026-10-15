"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { updateProfile, type Profile } from "@/lib/accountApi";
import { removeImages, uploadImage, validateImage } from "@/lib/storage";
import { announceProfile } from "@/lib/useProfile";
import { BIO_LIMIT, closeAction, initialValues, isDirty, profileUpdate, validateProfile } from "./editProfileForm";
import styles from "./page.module.css";

export default function EditProfileDialog({ profile, onClose }: { profile: Profile; onClose: () => void }) {
  const { user } = useAuth();
  const [initial] = useState(() => initialValues(profile));
  const [values, setValues] = useState(initial);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const keepEditingRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!avatarFile) return;
    const url = URL.createObjectURL(avatarFile);
    queueMicrotask(() => setAvatarPreview(url));
    return () => URL.revokeObjectURL(url);
  }, [avatarFile]);

  useEffect(() => {
    if (confirmingDiscard) keepEditingRef.current?.focus();
  }, [confirmingDiscard]);

  const dirty = isDirty(values, initial, { file: avatarFile, remove: removeAvatar });

  const requestClose = () => {
    const action = closeAction({ dirty, confirming: confirmingDiscard });
    if (action === "close") onClose();
    else setConfirmingDiscard(action === "confirm");
  };

  const set = (key: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setValues((current) => ({ ...current, [key]: event.target.value }));
    setFailure(null);
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors = validateProfile(values);
    if (avatarFile) {
      const problem = validateImage(avatarFile, "avatars");
      if (problem) nextErrors.avatar = problem;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length || !user) return;

    setSaving(true);
    setFailure(null);
    let uploaded: string | null = null;
    try {
      const update = profileUpdate(values);
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
      onClose();
    } catch (caught) {
      if (uploaded) removeImages("avatars", [uploaded]).catch(() => undefined);
      if (caught instanceof ApiError && caught.status === 409) {
        setErrors({ username: caught.message });
      } else {
        setFailure(caught instanceof Error ? caught.message : "That didn't save.");
      }
      setSaving(false);
    }
  };

  return (
    <Dialog
      title="Edit profile"
      subtitle="How you appear in Trekly."
      onClose={requestClose}
      busy={saving}
      sheet
      footer={
        confirmingDiscard ? (
          <div className={styles.confirmRow} role="alertdialog" aria-label="Discard changes">
            <span>Discard your unsaved changes?</span>
            <button ref={keepEditingRef} type="button" className={ui.secondary} onClick={() => setConfirmingDiscard(false)}>
              Keep editing
            </button>
            <button type="button" className={ui.danger} onClick={onClose}>
              Discard
            </button>
          </div>
        ) : (
          <>
            <button type="button" className={ui.ghost} onClick={requestClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" form="edit-profile-form" className={ui.primary} disabled={!dirty || saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </>
        )
      }
    >
      <form id="edit-profile-form" className={styles.form} onSubmit={save} noValidate>
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
            <input
              className={ui.input}
              value={values.display_name}
              onChange={set("display_name")}
              maxLength={60}
              autoComplete="name"
              data-autofocus
            />
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

        {failure && (
          <p className={ui.error} role="alert">
            {failure}
          </p>
        )}
      </form>
    </Dialog>
  );
}
