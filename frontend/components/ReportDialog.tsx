"use client";

import { useState, type FormEvent } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import profileStyles from "@/app/profile/page.module.css";
import { REPORT_REASONS, reportProfile, type ReportReason } from "@/lib/profilesApi";
import styles from "./ReportDialog.module.css";

/**
 * "Report profile", and "Report" on a trip note in a trail's "Hiked by"
 * section (pass `trailId`). Both go to the same endpoint and count against
 * the same daily limit; a note report also tells the team which note.
 */
export default function ReportDialog({
  username,
  name,
  trailId,
  onClose,
}: {
  username: string;
  name: string;
  /** Report this person's trip note on the trail, not their whole profile. */
  trailId?: string;
  onClose: () => void;
}) {
  const [reason, setReason] = useState<ReportReason | "">("");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const subject = trailId ? "trip note" : "profile";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!reason) {
      setResult({ ok: false, message: "Choose a reason." });
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      await reportProfile(username, reason, details, trailId);
      setResult({ ok: true, message: `Thanks. Our team will review this ${subject}.` });
    } catch (caught) {
      setResult({ ok: false, message: caught instanceof Error ? caught.message : "Your report didn't send. Try again." });
    } finally {
      setBusy(false);
    }
  };

  const sent = result?.ok;
  return (
    <Dialog
      title={trailId ? `Report ${name}'s trip note` : `Report ${name}`}
      subtitle="Reports go to the Trekly team. The person you report isn't told who sent it."
      onClose={onClose}
      busy={busy}
      size="sm"
      footer={
        sent ? (
          <button type="button" className={ui.primary} onClick={onClose}>
            Done
          </button>
        ) : (
          <>
            <button type="button" className={ui.ghost} onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button type="submit" form="report-form" className={ui.danger} disabled={busy}>
              {busy ? "Sending…" : "Send report"}
            </button>
          </>
        )
      }
    >
      {sent ? (
        <p className={ui.success} role="status">
          {result.message}
        </p>
      ) : (
        <form id="report-form" className={profileStyles.form} onSubmit={submit} noValidate>
          <fieldset className={styles.reasons}>
            <legend className={ui.label}>What&apos;s wrong with this {subject}?</legend>
            {REPORT_REASONS.map((option) => (
              <label key={option.value} className={styles.reason}>
                <input
                  type="radio"
                  name="reason"
                  value={option.value}
                  checked={reason === option.value}
                  onChange={() => setReason(option.value)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>
          <label className={ui.field}>
            <span className={ui.label}>Details (optional)</span>
            <textarea
              className={ui.input}
              rows={3}
              maxLength={1000}
              value={details}
              onChange={(event) => setDetails(event.target.value)}
            />
          </label>
          {result && (
            <p className={ui.error} role="alert">
              {result.message}
            </p>
          )}
        </form>
      )}
    </Dialog>
  );
}
