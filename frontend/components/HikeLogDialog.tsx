"use client";

import { useEffect, useId, useMemo, useState } from "react";
import Link from "next/link";
import DateInput from "./DateInput";
import Dialog from "./Dialog";
import ui from "./ui.module.css";
import { useAuth } from "./AuthProvider";
import { HIKE_NOTE_MAX, type HikeLog, type HikeLogInput } from "@/lib/hikeLogsApi";
import { undatedLabel } from "@/lib/hikeDate";
import { VERIFIED_LABEL } from "./VerifiedCheck";
import { PHOTO_ACCEPT, PHOTO_HINT, PREPARING_PHOTO, photoProblemMessage } from "@/lib/photoPrep";
import { preparePhoto } from "@/lib/preparePhoto";
import { processPhoto } from "@/lib/processPhoto";
import { formProblem, toast } from "@/lib/toast";
import { localToday } from "@/lib/stay";
import { removeImages, uploadHikePhoto } from "@/lib/storage";
import { useHikePhoto } from "@/lib/useHikePhoto";
import { activityBlocker, canShareHikes } from "@/lib/activity";
import { getPrivacy, type PrivacySettings } from "@/lib/profilesApi";
import { sectionHref } from "@/app/settings/settingsSections";
import { useNudge } from "@/lib/useNudge";
import Nudge from "./Nudge";
import styles from "./HikeLogDialog.module.css";

/**
 * Add or edit a Trail Journal entry: the date (or "I don't remember", for a
 * hike from before Trekly), an optional note and an optional photo. The photo is resized and re-encoded on the device (which
 * strips its GPS location) before it's uploaded to the user's private folder.
 */
export default function HikeLogDialog({
  trailName,
  entry,
  onSave,
  onRemove,
  onClose,
}: {
  trailName: string;
  entry: HikeLog | null;
  onSave: (input: HikeLogInput) => Promise<unknown>;
  onRemove: () => Promise<void>;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const today = localToday();
  const [date, setDate] = useState(entry?.hiked_on ?? today);
  // Only offered for an entry that's already undated or a new one.
  const [undated, setUndated] = useState(entry ? entry.hiked_on === null : false);
  const dateChanged = entry?.verified && (undated || date !== entry.hiked_on);
  const [note, setNote] = useState(entry?.note ?? "");
  // `undefined` keeps the saved photo; `null` removes it; a File replaces it.
  const [photo, setPhoto] = useState<File | null | undefined>(undefined);
  const [busy, setBusy] = useState<"save" | "remove" | null>(null);
  // Turning a picked photo upright and down to size, before its preview shows.
  const [preparing, setPreparing] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const noteId = useId();
  const photoId = useId();
  // "Share to Activity": ticked by default when their privacy settings share
  // activity (or, editing, when the hike is already posted).
  const [privacy, setPrivacy] = useState<PrivacySettings | null>(null);
  const [shareChoice, setShareChoice] = useState<boolean | null>(null);
  const shareAllowed = privacy !== null && canShareHikes(privacy);
  const share = shareChoice ?? (entry ? entry.shared : shareAllowed);
  useEffect(() => {
    const controller = new AbortController();
    getPrivacy(controller.signal)
      .then(setPrivacy)
      // Without settings the box stays off and nothing changes about sharing.
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  // "Sharing is off" with a toggle, for a new hike while feed sharing is off.
  // Shown until they put it away, turn sharing on, or save a hike with it showing.
  const nudge = useNudge("hike_share", !entry);
  const showNudge = nudge.show && privacy !== null && !privacy.share_activity;
  const turnOnSharing = async () => {
    const saved = await nudge.turnOn();
    if (!saved) return;
    setPrivacy(saved);
    setShareChoice(true);
  };

  const localPreview = useMemo(() => (photo instanceof File ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(() => (localPreview ? () => URL.revokeObjectURL(localPreview) : undefined), [localPreview]);
  const savedPhoto = useHikePhoto(photo === undefined ? (entry?.photo_path ?? null) : null);
  const preview = localPreview ?? savedPhoto;

  const save = async () => {
    if (!user) return;
    setBusy("save");
    setError(null);
    let uploaded: string | null = null;
    try {
      let photoPath = entry?.photo_path ?? null;
      if (photo instanceof File) {
        uploaded = await uploadHikePhoto(user.id, await processPhoto(photo));
        photoPath = uploaded;
      } else if (photo === null) {
        photoPath = null;
      }
      await onSave({
        hiked_on: undated ? null : date,
        note: note.trim() || null,
        photo_path: photoPath,
        // Only sent when it can take effect (or to take a post down).
        ...(shareAllowed || (entry?.shared && !share) ? { share } : {}),
      });
      // They saw the offer and decided: it doesn't come back.
      if (showNudge) nudge.dismiss();
      onClose();
    } catch (caught) {
      // Don't leave an orphaned upload behind if the entry didn't save.
      if (uploaded) await removeImages("hike-photos", [uploaded]).catch(() => undefined);
      const problem = formProblem(caught);
      if (problem) setError(problem);
      else toast.failure("save your hike", caught, () => void save());
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy("remove");
    setError(null);
    try {
      await onRemove();
      onClose();
    } catch (caught) {
      toast.failure("remove this hike", caught, () => void remove());
      setBusy(null);
    }
  };

  const footer = confirmRemove ? (
    <>
      <span className={styles.confirmText}>Remove this hike and its photo from your journal?</span>
      <button type="button" className={ui.ghost} onClick={() => setConfirmRemove(false)} disabled={busy !== null}>
        Keep it
      </button>
      <button type="button" className={ui.danger} onClick={() => void remove()} disabled={busy !== null}>
        {busy === "remove" ? "Removing…" : "Remove"}
      </button>
    </>
  ) : (
    <>
      {entry && (
        <button type="button" className={`${ui.ghost} ${styles.removeButton}`} onClick={() => setConfirmRemove(true)} disabled={busy !== null}>
          Remove from journal
        </button>
      )}
      <button type="button" className={ui.secondary} onClick={onClose} disabled={busy !== null}>
        Cancel
      </button>
      <button type="button" className={ui.primary} onClick={() => void save()} disabled={busy !== null || preparing || (!undated && !date)}>
        {busy === "save" ? "Saving…" : entry ? "Save changes" : "Add to journal"}
      </button>
    </>
  );

  return (
    <Dialog
      title={entry ? "Edit your hike" : "Mark as hiked"}
      subtitle={trailName}
      onClose={onClose}
      busy={busy !== null}
      footer={footer}
      sheet
    >
      <div className={styles.form}>
        <div className={ui.field}>
          <label className={ui.field}>
            <span className={ui.label}>Date hiked</span>
            <DateInput
              className={ui.input}
              value={undated ? "" : date}
              onChange={setDate}
              max={today}
              min="1900-01-01"
              required={!undated}
              disabled={undated}
              data-autofocus
            />
          </label>
          <label className={styles.undated}>
            <input type="checkbox" checked={undated} onChange={(event) => setUndated(event.target.checked)} />
            I don&apos;t remember the date
          </label>
          {undated && <span className={ui.hint}>It&apos;ll show as &ldquo;{undatedLabel(user?.created_at)}&rdquo;. Seasonal and date milestones need a date.</span>}
          {dateChanged && (
            <span className={ui.hint} role="status">
              This hike is {VERIFIED_LABEL.toLowerCase()}. Changing its date removes the check.
            </span>
          )}
        </div>

        <div className={ui.field}>
          <label className={ui.label} htmlFor={noteId}>
            Note <span className={styles.optional}>(optional)</span>
          </label>
          <textarea
            id={noteId}
            className={`${ui.input} ${styles.note}`}
            value={note}
            maxLength={HIKE_NOTE_MAX}
            rows={3}
            placeholder="Who you went with, what you saw…"
            onChange={(event) => setNote(event.target.value)}
          />
          <span className={ui.hint}>
            {note.length} / {HIKE_NOTE_MAX}
          </span>
        </div>

        <div className={ui.field}>
          <span className={ui.label}>
            Photo <span className={styles.optional}>(optional)</span>
          </span>
          {preview ? (
            <div className={styles.photoRow}>
              {/* eslint-disable-next-line @next/next/no-img-element -- signed or blob URL */}
              <img src={preview} alt="" className={styles.preview} />
              <div className={styles.photoActions}>
                <label htmlFor={photoId} className={ui.ghost}>
                  Replace
                </label>
                <button type="button" className={ui.ghost} onClick={() => setPhoto(null)}>
                  Remove photo
                </button>
              </div>
            </div>
          ) : (
            <label htmlFor={photoId} className={`${ui.secondary} ${styles.addPhoto}`}>
              Add a photo
            </label>
          )}
          <input
            id={photoId}
            type="file"
            accept={PHOTO_ACCEPT}
            className={ui.srOnly}
            disabled={preparing}
            onChange={async (event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (!file) return;
              setError(null);
              setPreparing(true);
              try {
                setPhoto(await preparePhoto(file));
              } catch (caught) {
                setError(photoProblemMessage(caught));
              } finally {
                setPreparing(false);
              }
            }}
          />
          <span className={ui.hint} aria-live="polite">
            {preparing
              ? PREPARING_PHOTO
              : `${PHOTO_HINT}. Location data is removed from photos before upload.`}
          </span>
        </div>

        <div className={ui.field}>
          <label className={`${styles.undated} ${!shareAllowed && !entry?.shared ? styles.shareOff : ""}`}>
            <input
              type="checkbox"
              checked={share && (shareAllowed || Boolean(entry?.shared))}
              disabled={!shareAllowed && !entry?.shared}
              onChange={(event) => setShareChoice(event.target.checked)}
            />
            Share to Activity
          </label>
          {showNudge ? (
            <Nudge
              control="switch"
              action="Share my activity"
              busy={nudge.busy}
              onTurnOn={() => void turnOnSharing()}
              onDismiss={nudge.dismiss}
            >
              Sharing is off. Turn it on to post this hike.
            </Nudge>
          ) : (
            <span className={ui.hint}>
              {privacy === null ? (
                "Shows this hike, with your note and photo, on the Activity page."
              ) : shareAllowed ? (
                <>
                  Shows this hike, with your note and photo, on the Activity page
                  {privacy.hide_hike_dates ? ", without the date" : ""}. Badges it earns are shared too.
                </>
              ) : (
                <>
                  {activityBlocker(privacy) ?? "Your activity isn't shared in the feed."}{" "}
                  <Link href={sectionHref("privacy")} className={styles.shareLink}>
                    Privacy settings
                  </Link>
                </>
              )}
            </span>
          )}
        </div>

        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
