"use client";

import { useId, type ReactNode } from "react";
import { X } from "lucide-react";
import styles from "./Nudge.module.css";

/**
 * A quiet pointer to a community setting: a line of text, one control that
 * turns the setting on (only when tapped), and ✕ to put it away for good.
 * `control` "switch" is an unticked inline toggle; "button" a text button.
 */
export default function Nudge({
  children,
  action,
  control = "button",
  busy = false,
  onTurnOn,
  onDismiss,
  card = false,
  className,
}: {
  children: ReactNode;
  /** The turn-on control's label, e.g. "Turn on sharing". */
  action: string;
  control?: "switch" | "button";
  busy?: boolean;
  onTurnOn: () => void;
  onDismiss: () => void;
  /** A small card (the Activity feed) instead of a line. */
  card?: boolean;
  className?: string;
}) {
  const textId = useId();
  return (
    <div className={`${card ? styles.card : styles.line} ${className ?? ""}`} role="group" aria-labelledby={textId}>
      <p id={textId} className={styles.text}>
        {children}
      </p>
      <div className={styles.actions}>
        {control === "switch" ? (
          <label className={styles.switchLabel}>
            <input
              type="checkbox"
              role="switch"
              className={styles.switch}
              checked={false}
              disabled={busy}
              onChange={(event) => {
                if (event.target.checked) onTurnOn();
              }}
            />
            {action}
          </label>
        ) : (
          <button type="button" className={card ? styles.primary : styles.link} disabled={busy} onClick={onTurnOn}>
            {busy ? "Turning on…" : action}
          </button>
        )}
        <button type="button" className={styles.close} onClick={onDismiss} disabled={busy} aria-label="Don't show this again" title="Don't show this again">
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
