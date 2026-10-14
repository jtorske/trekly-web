"use client";

import { useEffect, useRef, type ReactNode } from "react";
import styles from "./Dialog.module.css";

/**
 * Modal built on the native <dialog>: focus is trapped, Escape closes it and
 * the page behind is inert. Mount it to open; `onClose` fires on Escape,
 * the close button or a backdrop click.
 */
export default function Dialog({
  title,
  subtitle,
  onClose,
  children,
  footer,
  size = "md",
  busy = false,
}: {
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
  /** While busy (e.g. saving), Escape and backdrop clicks don't close it. */
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const busyRef = useRef(busy);
  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className={`${styles.dialog} ${styles[size]}`}
      aria-labelledby="dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busyRef.current) onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busyRef.current) onClose();
      }}
    >
      <div className={styles.inner}>
        <header className={styles.header}>
          <div>
            <h2 id="dialog-title" className={styles.title}>
              {title}
            </h2>
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
          >
            ×
          </button>
        </header>
        <div className={styles.body}>{children}</div>
        {footer && <footer className={styles.footer}>{footer}</footer>}
      </div>
    </dialog>
  );
}
