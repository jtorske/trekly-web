"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import UsernameField, { useUsernameStatus } from "@/components/UsernameField";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { updateProfile, type Profile } from "@/lib/accountApi";
import { validateAvatarFile } from "@/lib/avatarImage";
import { NOT_AN_IMAGE, readImageType } from "@/lib/imageType";
import type { ProcessedAvatar } from "@/lib/processAvatar";
import { removeImages, uploadAvatar } from "@/lib/storage";
import { announceProfile } from "@/lib/useProfile";
import { usernameReady } from "@/lib/usernames";
import AvatarCropper from "./AvatarCropper";
import { BIO_LIMIT, initialValues, isDirty, profileUpdate, staleAvatar, validateProfile } from "./editProfileForm";
import styles from "./settings.module.css";

/**
 * Settings → Edit profile: photo, display name, username, bio and home
 * region, saved together with one Save button. A new photo is cropped here
 * and only uploaded on Save.
 */
export default function EditProfileSection({ profile }: { profile: Profile }) {
  const { user } = useAuth();
  const [initial, setInitial] = useState(() => initialValues(profile));
  const [values, setValues] = useState(initial);
  // Picked but not yet cropped; then the processed 512px image awaiting Save.
  const [cropping, setCropping] = useState<File | null>(null);
  // A fresh cropper (zoom, position, load state) for every pick.
  const [cropKey, setCropKey] = useState(0);
  const [newAvatar, setNewAvatar] = useState<ProcessedAvatar | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const changePhotoRef = useRef<HTMLInputElement>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [triedSave, setTriedSave] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const usernameStatus = useUsernameStatus(values.username, profile.username);

  useEffect(() => {
    if (!newAvatar) return;
    const url = URL.createObjectURL(newAvatar.blob);
    queueMicrotask(() => setAvatarPreview(url));
    return () => URL.revokeObjectURL(url);
  }, [newAvatar]);

  // The photo controls only exist again once the crop step has unmounted.
  const wasCropping = useRef(false);
  useEffect(() => {
    if (wasCropping.current && !cropping) changePhotoRef.current?.focus();
    wasCropping.current = Boolean(cropping);
  }, [cropping]);

  const dirty = isDirty(values, initial, { file: newAvatar ?? cropping, remove: removeAvatar });

  // Leaving or reloading the page with unsaved changes asks first.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const hasPhoto = Boolean(newAvatar) || (Boolean(profile.avatar_path) && !removeAvatar);
  const name = profile.display_name || profile.username || "Your";

  const setFieldError = (field: string, problem: string | null) =>
    setErrors((current) => {
      const next = { ...current };
      if (problem) next[field] = problem;
      else delete next[field];
      return next;
    });

  const edited = () => {
    setFailure(null);
    setSaved(false);
  };

  const pickPhoto = async (file: File | undefined) => {
    if (!file) return;
    const problem = validateAvatarFile(file) ?? ((await readImageType(file)) ? null : NOT_AN_IMAGE);
    setFieldError("avatar", problem);
    if (problem) return;
    setCropKey((key) => key + 1);
    setCropping(file);
    edited();
  };

  // The browser couldn't decode it after all (e.g. a truncated file).
  const unreadablePhoto = () => {
    setCropping(null);
    setFieldError("avatar", NOT_AN_IMAGE);
  };

  const finishCrop = (image: ProcessedAvatar) => {
    setCropping(null);
    setNewAvatar(image);
    setRemoveAvatar(false);
  };

  const removePhoto = () => {
    setNewAvatar(null);
    setAvatarPreview(null);
    setRemoveAvatar(Boolean(profile.avatar_path));
    edited();
    changePhotoRef.current?.focus();
  };

  const discard = () => {
    setValues(initial);
    setCropping(null);
    setNewAvatar(null);
    setAvatarPreview(null);
    setRemoveAvatar(false);
    setErrors({});
    setTriedSave(false);
    setFailure(null);
  };

  const set = (key: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setValues((current) => ({ ...current, [key]: event.target.value }));
    edited();
  };

  const setUsername = (username: string) => {
    setValues((current) => ({ ...current, username }));
    setFieldError("username", null);
    edited();
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setTriedSave(true);
    const nextErrors = validateProfile(values);
    // The username field shows its own format and availability problems.
    delete nextErrors.username;
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length || !usernameReady(usernameStatus) || !user) return;

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
      const result = await updateProfile(update);
      const stale = staleAvatar(profile.avatar_path, result.avatar_path);
      if (stale) removeImages("avatars", [stale]).catch(() => undefined);
      announceProfile(result);
      const next = initialValues(result);
      setInitial(next);
      setValues(next);
      setNewAvatar(null);
      setAvatarPreview(null);
      setRemoveAvatar(false);
      setTriedSave(false);
      setSaved(true);
    } catch (caught) {
      if (uploaded) removeImages("avatars", [uploaded]).catch(() => undefined);
      if (caught instanceof ApiError && caught.status === 409) {
        setErrors({ username: caught.message });
      } else {
        setFailure(caught instanceof Error ? caught.message : "That didn't save.");
      }
    } finally {
      setSaving(false);
      setProgress(null);
    }
  };

  return (
    <form className={styles.form} onSubmit={save} noValidate aria-labelledby="settings-section-title">
      {cropping ? (
        <div className={styles.card}>
          <AvatarCropper
            key={cropKey}
            file={cropping}
            onCancel={() => setCropping(null)}
            onDone={finishCrop}
            onUnreadable={unreadablePhoto}
          />
        </div>
      ) : (
        <div className={`${styles.card} ${styles.identityCard}`}>
          <div className={styles.identity}>
            <Avatar
              path={removeAvatar ? null : profile.avatar_path}
              preview={avatarPreview}
              name={values.display_name || profile.display_name}
              email={profile.email}
              size={64}
              alt={`${name}'s profile photo`}
            />
            <div className={styles.identityText}>
              {profile.username && <span className={styles.identityUsername}>@{profile.username}</span>}
              <span className={styles.identityName}>{profile.display_name || "No display name yet"}</span>
            </div>
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
              <label htmlFor="avatar-input" className={ui.primary}>
                {hasPhoto ? "Change photo" : "Add photo"}
              </label>
              {hasPhoto && (
                <button type="button" className={ui.ghost} onClick={removePhoto} disabled={saving}>
                  Remove photo
                </button>
              )}
            </div>
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
      )}

      <div className={styles.card}>
        <label className={ui.field}>
          <span className={ui.label}>Display name</span>
          <input
            className={ui.input}
            value={values.display_name}
            onChange={set("display_name")}
            maxLength={60}
            autoComplete="name"
          />
        </label>

        <div className={styles.usernameField}>
          <UsernameField
            id="settings-username"
            value={values.username}
            onChange={setUsername}
            status={usernameStatus}
            suggestFrom=""
            showError={triedSave}
          />
          {errors.username && (
            <span className={ui.fieldError} role="alert">
              {errors.username}
            </span>
          )}
        </div>

        <label className={ui.field}>
          <span className={styles.labelRow}>
            <span className={ui.label}>Bio</span>
            <span className={values.bio.length > BIO_LIMIT ? ui.fieldError : ui.hint} aria-live="polite">
              {values.bio.length}/{BIO_LIMIT}
            </span>
          </span>
          <textarea className={ui.input} rows={4} value={values.bio} onChange={set("bio")} aria-invalid={Boolean(errors.bio)} />
          {errors.bio && <span className={ui.fieldError}>{errors.bio}</span>}
        </label>

        <label className={ui.field}>
          <span className={ui.label}>Home region (optional)</span>
          <input
            className={ui.input}
            value={values.home_region}
            onChange={set("home_region")}
            maxLength={80}
            placeholder="e.g. Pacific Northwest"
          />
        </label>

        {failure && (
          <p className={ui.error} role="alert">
            {failure}
          </p>
        )}
        <div className={styles.formActions}>
          <p className={styles.saveStatus} role="status" aria-live="polite">
            {saved && !dirty ? "Saved." : ""}
          </p>
          {dirty && (
            <button type="button" className={ui.ghost} onClick={discard} disabled={saving}>
              Discard changes
            </button>
          )}
          <button type="submit" className={ui.primary} disabled={!dirty || saving || Boolean(cropping)}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </form>
  );
}
