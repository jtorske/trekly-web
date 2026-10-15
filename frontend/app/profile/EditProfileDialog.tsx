"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { updateProfile, type Profile } from "@/lib/accountApi";
import { validateAvatarFile } from "@/lib/avatarImage";
import type { ProcessedAvatar } from "@/lib/processAvatar";
import { removeImages, uploadAvatar } from "@/lib/storage";
import { announceProfile } from "@/lib/useProfile";
import AvatarCropper from "./AvatarCropper";
import { BIO_LIMIT, closeAction, initialValues, isDirty, profileUpdate, staleAvatar, validateProfile } from "./editProfileForm";
import styles from "./page.module.css";

export default function EditProfileDialog({ profile, onClose }: { profile: Profile; onClose: () => void }) {
  const { user } = useAuth();
  const [initial] = useState(() => initialValues(profile));
  const [values, setValues] = useState(initial);
  // Picked but not yet cropped; then the processed 512px image awaiting Save.
  const [cropping, setCropping] = useState<File | null>(null);
  const [newAvatar, setNewAvatar] = useState<ProcessedAvatar | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const changePhotoRef = useRef<HTMLInputElement>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const keepEditingRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!newAvatar) return;
    const url = URL.createObjectURL(newAvatar.blob);
    queueMicrotask(() => setAvatarPreview(url));
    return () => URL.revokeObjectURL(url);
  }, [newAvatar]);

  useEffect(() => {
    if (confirmingDiscard) keepEditingRef.current?.focus();
  }, [confirmingDiscard]);

  // The photo controls only exist again once the crop step has unmounted.
  const wasCropping = useRef(false);
  useEffect(() => {
    if (wasCropping.current && !cropping) changePhotoRef.current?.focus();
    wasCropping.current = Boolean(cropping);
  }, [cropping]);

  const dirty = isDirty(values, initial, { file: newAvatar ?? cropping, remove: removeAvatar });
  const hasPhoto = Boolean(newAvatar) || (Boolean(profile.avatar_path) && !removeAvatar);
  const photoAlt = `${values.display_name.trim() || profile.display_name || "Your"}'s profile photo`;

  const pickPhoto = (file: File | undefined) => {
    if (!file) return;
    const problem = validateAvatarFile(file);
    setErrors((current) => {
      const next = { ...current };
      if (problem) next.avatar = problem;
      else delete next.avatar;
      return next;
    });
    if (!problem) setCropping(file);
  };

  const finishCrop = (image: ProcessedAvatar) => {
    setCropping(null);
    setNewAvatar(image);
    setRemoveAvatar(false);
    setFailure(null);
  };

  const removePhoto = () => {
    setNewAvatar(null);
    setAvatarPreview(null);
    setRemoveAvatar(Boolean(profile.avatar_path));
    setFailure(null);
    changePhotoRef.current?.focus();
  };

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
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length || !user) return;

    setSaving(true);
    setFailure(null);
    let uploaded: string | null = null;
    try {
      const update = profileUpdate(values);
      if (newAvatar) {
        setProgress(0);
        uploaded = await uploadAvatar(user.id, newAvatar, setProgress);
        update.avatar_path = uploaded;
      } else if (removeAvatar) {
        update.avatar_path = null;
      }
      const saved = await updateProfile(update);
      const stale = staleAvatar(profile.avatar_path, saved.avatar_path);
      if (stale) removeImages("avatars", [stale]).catch(() => undefined);
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
      setProgress(null);
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
            <button type="submit" form="edit-profile-form" className={ui.primary} disabled={!dirty || saving || Boolean(cropping)}>
              {saving ? "Saving…" : "Save"}
            </button>
          </>
        )
      }
    >
      <form id="edit-profile-form" className={styles.form} onSubmit={save} noValidate>
        {cropping ? (
          <AvatarCropper file={cropping} onCancel={() => setCropping(null)} onDone={finishCrop} />
        ) : (
          <div className={styles.avatarRow}>
            <Avatar
              path={removeAvatar ? null : profile.avatar_path}
              preview={avatarPreview}
              name={values.display_name || profile.display_name}
              email={profile.email}
              size={88}
              alt={photoAlt}
            />
            <div className={styles.photoControls}>
              <span className={ui.label} id="photo-label">
                Profile photo
              </span>
              <div className={styles.photoButtons}>
                <input
                  ref={changePhotoRef}
                  id="avatar-input"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className={`${ui.srOnly} ${styles.fileInput}`}
                  aria-describedby="photo-hint"
                  disabled={saving}
                  onChange={(event) => {
                    pickPhoto(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                <label htmlFor="avatar-input" className={ui.secondary}>
                  {hasPhoto ? "Change photo" : "Add photo"}
                </label>
                {hasPhoto && (
                  <button type="button" className={ui.ghost} onClick={removePhoto} disabled={saving}>
                    Remove photo
                  </button>
                )}
              </div>
              <span id="photo-hint" className={ui.hint}>
                {newAvatar
                  ? "New photo — it replaces your current one when you save."
                  : removeAvatar
                    ? "Your photo will be removed when you save."
                    : "JPEG, PNG or WebP up to 5 MB."}
              </span>
              {errors.avatar && (
                <span className={ui.fieldError} role="alert">
                  {errors.avatar}
                </span>
              )}
              {progress !== null && (
                <div className={styles.progress}>
                  <progress max={1} value={progress} aria-label="Uploading photo" />
                  <span className={ui.hint} aria-hidden="true">
                    {Math.round(progress * 100)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

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
