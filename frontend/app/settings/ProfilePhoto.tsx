"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Camera, ImageUp, LoaderCircle, Trash2 } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import Avatar from "@/components/Avatar";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { updateProfile, type Profile } from "@/lib/accountApi";
import { AvatarCleanupError, REMOVE_FAILED, removeAvatar, replaceAvatar, type AvatarSteps } from "@/lib/avatarChange";
import { validateAvatarFile } from "@/lib/avatarImage";
import { NOT_AN_IMAGE, readImageType } from "@/lib/imageType";
import type { ProcessedAvatar } from "@/lib/processAvatar";
import { deleteImages, uploadAvatar } from "@/lib/storage";
import { announceProfile } from "@/lib/useProfile";
import AvatarCropper from "./AvatarCropper";
import styles from "./ProfilePhoto.module.css";

/** The real Storage and API calls behind lib/avatarChange.ts. */
function avatarSteps(userId: string): AvatarSteps {
  return {
    upload: (image, onProgress) => uploadAvatar(userId, image, onProgress),
    update: updateProfile,
    remove: (paths) => deleteImages("avatars", paths),
    announce: announceProfile,
  };
}

const PHONE = "(max-width: 767px)";
const subscribePhone = (onChange: () => void) => {
  const query = window.matchMedia(PHONE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
};
const isPhone = () => window.matchMedia(PHONE).matches;

/**
 * The owner's profile photo as a button that changes it: a small menu
 * (a modal on phones) to upload a new photo (picked, cropped, then saved
 * straight away) or remove the current one. Used on /profile and in
 * Settings → Edit profile, so both save photos the same way.
 *
 * Returns the pieces for the caller to place: `avatar` (the button and its
 * menu), `open` (for a separate "Change photo" button), and `status`
 * (progress and errors, as a live region).
 */
export function useProfilePhoto(profile: Profile, { size, alt }: { size: number; alt: string }) {
  const { user } = useAuth();
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const phone = useSyncExternalStore(subscribePhone, isPhone, () => false);

  const [menu, setMenu] = useState<"closed" | "open" | "confirmRemove">("closed");
  // Picked and checked, waiting for the crop; a fresh cropper for every pick.
  const [cropping, setCropping] = useState<{ file: File; key: number } | null>(null);
  const [saving, setSaving] = useState<"upload" | "remove" | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryPath, setRetryPath] = useState<string | null>(null);

  const hasPhoto = Boolean(profile.avatar_path);
  const busy = saving !== null;

  const closeMenu = (returnFocus: boolean) => {
    setMenu("closed");
    if (returnFocus) triggerRef.current?.focus();
  };

  const open = () => {
    if (busy) return;
    setMenu("open");
  };

  // The popover (not the phone modal, which handles this itself) closes on
  // an outside click, and starts with focus on its first item.
  useEffect(() => {
    if (menu === "closed" || phone) return;
    menuRef.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) setMenu("closed");
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [menu, phone]);

  const choosePhoto = () => {
    setError(null);
    setRetryPath(null);
    setMenu("closed");
    // After the phone modal has closed (it makes the page behind inert); the
    // tap still counts as the user's, so the browser lets the picker open.
    setTimeout(() => inputRef.current?.click(), 0);
  };

  const pickPhoto = async (file: File | undefined) => {
    if (!file) return;
    const problem = validateAvatarFile(file) ?? ((await readImageType(file)) ? null : NOT_AN_IMAGE);
    if (problem) {
      setError(problem);
      return;
    }
    setCropping((current) => ({ file, key: (current?.key ?? 0) + 1 }));
  };

  const savePhoto = async (image: ProcessedAvatar) => {
    setCropping(null);
    if (!user) return;
    const url = URL.createObjectURL(image.blob);
    setPreview(url);
    setSaving("upload");
    setProgress(0);
    setError(null);
    try {
      await replaceAvatar(avatarSteps(user.id), profile.avatar_path, image, setProgress);
    } catch (caught) {
      setError(caught instanceof Error ? `Your photo didn't save. ${caught.message}` : "Your photo didn't save. Try again.");
    } finally {
      URL.revokeObjectURL(url);
      setPreview(null);
      setSaving(null);
      setProgress(null);
      triggerRef.current?.focus();
    }
  };

  const removePhoto = async () => {
    const previous = profile.avatar_path;
    setMenu("closed");
    if (!user || !previous) return;
    setSaving("remove");
    setError(null);
    try {
      await removeAvatar(avatarSteps(user.id), previous);
      setRetryPath(null);
    } catch (caught) {
      if (caught instanceof AvatarCleanupError) setRetryPath(caught.retryPath);
      setError(caught instanceof Error ? caught.message : "Your photo wasn't removed. Try again.");
    } finally {
      setSaving(null);
      triggerRef.current?.focus();
    }
  };

  // The photo is already off the profile; only its file is left to delete.
  const retryDelete = async () => {
    if (!retryPath) return;
    setSaving("remove");
    try {
      await deleteImages("avatars", [retryPath]);
      setRetryPath(null);
      setError(null);
    } catch {
      setError(REMOVE_FAILED);
    } finally {
      setSaving(null);
    }
  };

  const onMenuKeyDown = (event: KeyboardEvent) => {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const index = items.indexOf(document.activeElement as HTMLElement);
    const move = (next: number) => {
      event.preventDefault();
      items[(next + items.length) % items.length]?.focus();
    };
    if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(items.length - 1);
    else if (event.key === "Escape") {
      event.preventDefault();
      closeMenu(true);
    } else if (event.key === "Tab") closeMenu(false);
  };

  const choices: ReactNode =
    menu === "confirmRemove" ? (
      <div className={styles.confirm} role="group" aria-label="Remove photo">
        <p>Remove your profile photo? Your initials show instead.</p>
        <div className={styles.confirmActions}>
          <button type="button" className={ui.danger} onClick={removePhoto} data-autofocus>
            Remove
          </button>
          <button type="button" className={ui.ghost} onClick={() => setMenu("open")}>
            Keep photo
          </button>
        </div>
      </div>
    ) : (
      <>
        <button type="button" role="menuitem" tabIndex={-1} className={styles.item} onClick={choosePhoto} data-autofocus>
          <ImageUp size={18} aria-hidden="true" />
          Upload new photo
        </button>
        {hasPhoto && (
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            className={`${styles.item} ${styles.danger}`}
            onClick={() => setMenu("confirmRemove")}
          >
            <Trash2 size={18} aria-hidden="true" />
            Remove photo
          </button>
        )}
        <button type="button" role="menuitem" tabIndex={-1} className={styles.item} onClick={() => closeMenu(true)}>
          Cancel
        </button>
      </>
    );

  const label = busy
    ? saving === "upload"
      ? "Saving your new photo"
      : "Removing your photo"
    : hasPhoto
      ? "Change profile photo"
      : "Add a profile photo";

  const avatar = (
    <div className={styles.wrap}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        style={{ "--photo-size": `${size}px` } as CSSProperties}
        aria-label={label}
        aria-haspopup={phone ? "dialog" : "menu"}
        aria-expanded={menu !== "closed"}
        aria-controls={menu !== "closed" && !phone ? menuId : undefined}
        aria-busy={busy}
        disabled={busy}
        onClick={() => (menu === "closed" ? open() : closeMenu(false))}
      >
        <Avatar path={profile.avatar_path} preview={preview} name={profile.display_name} email={profile.email} size={size} alt={alt} />
        <span className={`${styles.overlay} ${busy ? styles.overlayBusy : ""}`} aria-hidden="true">
          {busy ? (
            <>
              <LoaderCircle className={styles.spinner} size={24} />
              {progress !== null && <span className={styles.overlayText}>{Math.round(progress * 100)}%</span>}
            </>
          ) : (
            <>
              <Camera size={22} />
              <span className={styles.overlayText}>{hasPhoto ? "Change photo" : "Add photo"}</span>
            </>
          )}
        </span>
        {!busy && (
          <span className={styles.badge} aria-hidden="true">
            <Camera size={14} />
          </span>
        )}
      </button>

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className={ui.srOnly}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          pickPhoto(event.target.files?.[0]);
          event.target.value = "";
        }}
      />

      {menu !== "closed" && !phone && (
        <div ref={menuRef} id={menuId} role="menu" aria-label="Profile photo" className={styles.menu} onKeyDown={onMenuKeyDown}>
          {choices}
        </div>
      )}

      {menu !== "closed" && phone && (
        <Dialog title="Profile photo" size="sm" onClose={() => closeMenu(true)}>
          <div ref={menuRef} role="menu" aria-label="Profile photo" className={styles.sheet} onKeyDown={onMenuKeyDown}>
            {choices}
          </div>
        </Dialog>
      )}

      {cropping && (
        <Dialog title="Crop your photo" subtitle="Drag to position it, and zoom to fit." size="sm" onClose={() => setCropping(null)}>
          <AvatarCropper
            key={cropping.key}
            file={cropping.file}
            onCancel={() => setCropping(null)}
            onDone={savePhoto}
            onUnreadable={() => {
              setCropping(null);
              setError(NOT_AN_IMAGE);
            }}
          />
        </Dialog>
      )}
    </div>
  );

  const status = (
    <div className={styles.status} aria-live="polite">
      {saving === "upload" && <span className={ui.hint}>Saving your new photo…</span>}
      {saving === "remove" && <span className={ui.hint}>Removing your photo…</span>}
      {error && (
        <p className={ui.error} role="alert">
          {error}{" "}
          {retryPath && (
            <button type="button" className={ui.ghost} onClick={retryDelete} disabled={busy}>
              Try again
            </button>
          )}
        </p>
      )}
    </div>
  );

  return { avatar, open, status, hasPhoto, busy };
}
