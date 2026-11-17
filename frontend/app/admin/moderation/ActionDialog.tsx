"use client";

import { useState } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import styles from "../admin.module.css";

export interface ModerationAction {
  title: string;
  body: string;
  confirm: string;
  danger: boolean;
  /** Ask for a reason: required, and sent to the author where the action emails them. */
  reason?: { label: string; placeholder?: string };
  /** Ask for a number of days (a suspension). */
  days?: boolean;
}

/**
 * One moderation action: what will happen, the reason (and days), and an
 * explicit confirm. A failure stays in the dialog; success closes it.
 */
export default function ActionDialog({
  action,
  onConfirm,
  onClose,
}: {
  action: ModerationAction;
  onConfirm: (input: { reason: string; days: number }) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [days, setDays] = useState("7");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dayCount = Number.parseInt(days, 10);
  const ready = (!action.reason || reason.trim()) && (!action.days || (dayCount >= 1 && dayCount <= 365));

  const confirm = async () => {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm({ reason: reason.trim(), days: dayCount });
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't work. Try again.");
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={action.title}
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
            className={action.danger ? ui.danger : ui.primary}
            onClick={confirm}
            disabled={busy || !ready}
            data-autofocus={action.reason || action.days ? undefined : true}
          >
            {busy ? "Working…" : action.confirm}
          </button>
        </>
      }
    >
      <div className={styles.confirmBody}>
        <p>{action.body}</p>
        {action.days && (
          <label className={ui.field}>
            <span className={ui.label}>Days</span>
            <input
              className={ui.input}
              type="number"
              inputMode="numeric"
              min={1}
              max={365}
              value={days}
              onChange={(event) => setDays(event.target.value)}
            />
          </label>
        )}
        {action.reason && (
          <label className={ui.field}>
            <span className={ui.label}>{action.reason.label}</span>
            <textarea
              className={ui.input}
              rows={3}
              value={reason}
              placeholder={action.reason.placeholder}
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
