"use client";

import { useEffect, useId, useMemo, useState } from "react";
import DateInput from "./DateInput";
import Dialog from "./Dialog";
import ui from "./ui.module.css";
import { useAuth } from "./AuthProvider";
import { HIKE_NOTE_MAX, type HikeLog, type HikeLogInput } from "@/lib/hikeLogsApi";
import { photoInputProblem } from "@/lib/journalPhoto";
import { processPhoto } from "@/lib/processPhoto";
import { formProblem, toast } from "@/lib/toast";
import { localToday } from "@/lib/stay";
import { removeImages, uploadHikePhoto } from "@/lib/storage";
import { useHikePhoto } from "@/lib/useHikePhoto";
import styles from "./HikeLogDialog.module.css";

/**
 * Add or edit a Trail Journal entry: the date, an optional note and an
 * optional photo. The photo is resized and re-encoded on the device (which
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
  const [note, setNote] = useState(entry?.note ?? "");
  // `undefined` keeps the saved photo; `null` removes it; a File replaces it.
  const [photo, setPhoto] = useState<File | null | undefined>(undefined);
  const [busy, setBusy] = useState<"save" | "remove" | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const noteId = useId();
  const photoId = useId();

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
      await onSave({ hiked_on: date, note: note.trim() || null, photo_path: photoPath });
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
      <button type="button" className={ui.primary} onClick={() => void save()} disabled={busy !== null || !date}>
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
        <label className={ui.field}>
          <span className={ui.label}>Date hiked</span>
          <DateInput className={ui.input} value={date} onChange={setDate} max={today} min="1900-01-01" required data-autofocus />
        </label>

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
            accept="image/jpeg,image/png,image/webp"
            className={ui.srOnly}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (!file) return;
              const problem = photoInputProblem(file);
              if (problem) {
                setError(problem);
                return;
              }
              setError(null);
              setPhoto(file);
            }}
          />
          <span className={ui.hint}>Only you can see your journal. Location data is removed from photos before upload.</span>
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
