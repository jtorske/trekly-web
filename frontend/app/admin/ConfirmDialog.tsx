"use client";

import { useState } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import type { Confirmation } from "@/lib/adminView";
import styles from "./admin.module.css";

/**
 * Every admin action goes through this: what will happen, an optional reason
 * (kept in the audit log), and an explicit confirm button. A failure stays in
 * the dialog so it can be retried; success closes it.
 */
export default function ConfirmDialog({
  confirmation,
  onConfirm,
  onClose,
}: {
  confirmation: Confirmation;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm(reason.trim());
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't work. Try again.");
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={confirmation.title}
      onClose={onClose}
      busy={busy}
      size="sm"
      footer={
        <>
          <button type="button" className={ui.ghost} onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={confirmation.danger ? ui.danger : ui.primary}
            onClick={confirm}
            disabled={busy}
            data-autofocus={confirmation.reason ? undefined : true}
          >
            {busy ? "Working…" : confirmation.confirm}
          </button>
        </>
      }
    >
      <div className={styles.confirmBody}>
        <p>{confirmation.body}</p>
        {confirmation.reason && (
          <label className={ui.field}>
            <span className={ui.label}>Reason (optional, only admins see it)</span>
            <input
              className={ui.input}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={500}
              data-autofocus
            />
          </label>
        )}
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
