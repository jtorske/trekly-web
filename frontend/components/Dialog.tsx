"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import styles from "./Dialog.module.css";

/**
 * Modal built on the native <dialog>: focus is trapped, Escape closes it and
 * the page behind is inert and doesn't scroll. Mount it to open; `onClose`
 * fires on Escape, the close button or a backdrop click. Focus starts on the
 * element marked `data-autofocus` (if any) and returns to the opener on unmount.
 */
export default function Dialog({
  title,
  subtitle,
  onClose,
  children,
  footer,
  size = "md",
  busy = false,
  sheet = false,
}: {
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
  /** While busy (e.g. saving), Escape and backdrop clicks don't close it. */
  busy?: boolean;
  /** On phones, fill the screen and keep the footer above the keyboard. */
  sheet?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const busyRef = useRef(busy);
  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  const unmounting = useRef(false);

  useEffect(() => {
    unmounting.current = false;
    const dialog = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";
    if (dialog && !dialog.open) {
      dialog.showModal();
      // showModal() focuses the first focusable element (the close button);
      // React's autoFocus never reaches the DOM, so honour a marker instead.
      dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    return () => {
      unmounting.current = true;
      dialog?.close();
      root.style.overflow = previousOverflow;
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  // Mobile keyboards shrink the visual viewport without resizing the layout
  // viewport, so size the sheet to what's actually visible.
  useEffect(() => {
    const dialog = ref.current;
    const viewport = window.visualViewport;
    if (!sheet || !dialog || !viewport) return;
    const fit = () => {
      dialog.style.setProperty("--sheet-height", `${viewport.height}px`);
      dialog.style.setProperty("--sheet-top", `${viewport.offsetTop}px`);
    };
    fit();
    viewport.addEventListener("resize", fit);
    viewport.addEventListener("scroll", fit);
    return () => {
      viewport.removeEventListener("resize", fit);
      viewport.removeEventListener("scroll", fit);
    };
  }, [sheet]);

  return (
    <dialog
      ref={ref}
      className={`${styles.dialog} ${styles[size]} ${sheet ? styles.sheet : ""}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      // Escape is handled on keydown: cancelling it there means the browser
      // never raises a close request. Refusing those via `cancel` instead
      // makes Chrome force-close the dialog on a second Escape.
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        if (!busyRef.current) onClose();
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!busyRef.current) onClose();
      }}
      // A close we didn't ask for (e.g. repeated Android back gestures):
      // reopen and route it through onClose so unsaved-changes checks run.
      onClose={() => {
        const dialog = ref.current;
        if (unmounting.current || !dialog || dialog.open) return;
        dialog.showModal();
        if (!busyRef.current) onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busyRef.current) onClose();
      }}
    >
      <div className={styles.inner}>
        <header className={styles.header}>
          <div>
            <h2 id={titleId} className={styles.title}>
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
