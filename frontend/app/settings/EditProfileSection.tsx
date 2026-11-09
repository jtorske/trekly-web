"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import UsernameField, { useUsernameStatus } from "@/components/UsernameField";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { updateProfile, type Profile } from "@/lib/accountApi";
import { toast } from "@/lib/toast";
import { announceProfile } from "@/lib/useProfile";
import { province, provinceOptions, type ProvinceCode } from "@/lib/provinces";
import ProvinceBadge from "@/components/ProvinceBadge";
import { usernameReady } from "@/lib/usernames";
import { BIO_LIMIT, initialValues, isDirty, profileUpdate, validateProfile } from "./editProfileForm";
import { useProfilePhoto } from "./ProfilePhoto";
import { PHOTO_HINT } from "@/lib/photoPrep";
import { sectionHref } from "./settingsSections";
import styles from "./settings.module.css";

/**
 * Settings → Edit profile: display name, username, bio, home province and
 * home region,
 * saved together with one Save button. The photo saves on its own, straight
 * away, with the same control as the profile page's avatar (ProfilePhoto).
 */
export default function EditProfileSection({ profile }: { profile: Profile }) {
  const { user } = useAuth();
  const [initial, setInitial] = useState(() => initialValues(profile));
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [triedSave, setTriedSave] = useState(false);
  const [saving, setSaving] = useState(false);
  const usernameStatus = useUsernameStatus(values.username, profile.username);
  const name = profile.display_name || profile.username || "Your";
  const photo = useProfilePhoto(profile, { size: 64, alt: `${name}'s profile photo` });

  const dirty = isDirty(values, initial);
  const home = province(values.home_province);

  // Leaving or reloading the page with unsaved changes asks first.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const setFieldError = (field: string, problem: string | null) =>
    setErrors((current) => {
      const next = { ...current };
      if (problem) next[field] = problem;
      else delete next[field];
      return next;
    });

  const discard = () => {
    setValues(initial);
    setErrors({});
    setTriedSave(false);
  };

  const set = (key: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setValues((current) => ({ ...current, [key]: event.target.value }));
  };

  const setUsername = (username: string) => {
    setValues((current) => ({ ...current, username }));
    setFieldError("username", null);
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
    try {
      const result = await updateProfile(profileUpdate(values));
      announceProfile(result);
      const next = initialValues(result);
      setInitial(next);
      setValues(next);
      setTriedSave(false);
      const renamed = result.username && result.username !== profile.username;
      toast.success(renamed ? `Username changed to @${result.username}` : "Profile saved");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setErrors({ username: caught.message });
      } else {
        toast.failure("save your profile", caught);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={save} noValidate aria-labelledby="settings-section-title">
      <div className={`${styles.card} ${styles.identityCard}`}>
        <div className={styles.identity}>
          {photo.avatar}
          <div className={styles.identityText}>
            {profile.username && <span className={styles.identityUsername}>@{profile.username}</span>}
            <span className={styles.identityName}>{profile.display_name || "No display name yet"}</span>
          </div>
          <div className={styles.photoButtons}>
            <button type="button" className={ui.primary} onClick={photo.open} disabled={photo.busy} aria-describedby="photo-hint">
              {photo.hasPhoto ? "Change photo" : "Add photo"}
            </button>
          </div>
        </div>
        <span id="photo-hint" className={ui.hint}>
          {PHOTO_HINT}. Photo changes save straight away.
        </span>
        {photo.status}
      </div>

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

        <div className={styles.provinceField}>
          <label className={ui.field}>
            <span className={ui.label}>Home province or territory</span>
            <select
              className={ui.input}
              value={values.home_province}
              onChange={(event) => setValues((current) => ({ ...current, home_province: event.target.value as ProvinceCode | "" }))}
              aria-describedby="province-hint"
            >
              <option value="">Prefer not to say</option>
              {provinceOptions().map((group) => (
                <optgroup key={group.label} label={group.label}>
                  {group.options.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          {home && <ProvinceBadge province={home} decorative className={styles.provincePreview} />}
          <span id="province-hint" className={`${ui.hint} ${styles.provinceHint}`}>
            Shows on your profile with its own badge. Visitors see it only once you turn on{" "}
            <Link href={sectionHref("privacy")}>Home province</Link> in Privacy.
          </span>
        </div>

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

        <div className={styles.formActions}>
          {dirty && (
            <button type="button" className={ui.ghost} onClick={discard} disabled={saving}>
              Discard changes
            </button>
          )}
          <button type="submit" className={ui.primary} disabled={!dirty || saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </form>
  );
}
