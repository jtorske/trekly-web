"use client";

import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type PointerEvent } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import {
  getServerToasts,
  getToasts,
  pauseToasts,
  resumeToasts,
  subscribeToasts,
  toast as toastApi,
  type Toast,
} from "@/lib/toast";
import { flushRemovals } from "@/lib/undo";
import styles from "./Toaster.module.css";

const ICONS = { success: CircleCheck, error: CircleAlert, info: Info } as const;
const SWIPE_DISMISS_PX = 64;

/**
 * Renders the toast store (lib/toast). Mounted once in the root layout.
 *
 * The stack is a manual popover so it sits in the top layer, re-raised
 * whenever a toast arrives. A modal <dialog> makes everything outside it
 * inert, popovers included, so while one is open the stack renders inside
 * the topmost one and its buttons stay usable. Screen readers
 * hear toasts through two live regions that stay mounted: polite for success
 * and info, assertive for errors. F8 jumps to the newest toast.
 */
export default function Toaster() {
  const toasts = useSyncExternalStore(subscribeToasts, getToasts, getServerToasts);
  const stackRef = useRef<HTMLElement>(null);
  const [polite, setPolite] = useState("");
  const [assertive, setAssertive] = useState("");
  const announced = useRef(new Set<number>());
  const newest = toasts.at(-1)?.id ?? 0;
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const update = () => {
      const modals = [...document.querySelectorAll("dialog")].filter((d) => d.open && d.matches(":modal"));
      setHost(modals.at(-1) ?? null);
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["open"] });
    return () => observer.disconnect();
  }, []);

  // Announce each toast once. Clearing first makes a repeated message speak again.
  useEffect(() => {
    for (const t of toasts) {
      if (announced.current.has(t.id)) continue;
      announced.current.add(t.id);
      const text = t.action ? `${t.message} ${t.action.label} available. Press F8 to reach it.` : t.message;
      const set = t.type === "error" ? setAssertive : setPolite;
      set("");
      window.setTimeout(() => set(text), 50);
    }
  }, [toasts]);

  useLayoutEffect(() => {
    const stack = stackRef.current;
    if (!stack || typeof stack.showPopover !== "function") return;
    if (toasts.length === 0) {
      if (stack.matches(":popover-open")) stack.hidePopover();
      return;
    }
    // Re-open so the stack is the newest top-layer element, above any dialog.
    if (stack.matches(":popover-open")) stack.hidePopover();
    stack.showPopover();
  }, [toasts.length, newest, host]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "F8") return;
      const target = stackRef.current?.querySelector<HTMLElement>("li:last-child button, li:last-child a");
      if (!target) return;
      event.preventDefault();
      target.focus();
    };
    // A delete still waiting on its Undo toast goes out before the page unloads.
    const onHide = () => flushRemovals();
    window.addEventListener("keydown", onKey);
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pagehide", onHide);
    };
  }, []);

  const content = (
    <>
      <section
        ref={stackRef}
        popover="manual"
        aria-label="Notifications"
        className={styles.stack}
        onPointerEnter={(event) => event.pointerType === "mouse" && pauseToasts()}
        onPointerLeave={(event) => event.pointerType === "mouse" && resumeToasts()}
        onFocus={pauseToasts}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) resumeToasts();
        }}
      >
        <ol className={styles.list}>
          {toasts.map((t) => (
            <ToastCard key={t.id} toast={t} />
          ))}
        </ol>
      </section>
      <div className={styles.srOnly} role="status" aria-live="polite" aria-atomic="true">
        {polite}
      </div>
      <div className={styles.srOnly} role="alert" aria-live="assertive" aria-atomic="true">
        {assertive}
      </div>
    </>
  );

  // Inside an open modal dialog nothing else is reachable, live regions included.
  return host ? createPortal(content, host) : content;
}

function ToastCard({ toast }: { toast: Toast }) {
  const Icon = ICONS[toast.type];
  const drag = useRef<{ x: number; pointer: number } | null>(null);
  const [offset, setOffset] = useState(0);

  const onPointerDown = (event: PointerEvent<HTMLLIElement>) => {
    if (event.pointerType === "mouse" || (event.target as HTMLElement).closest("button, a")) return;
    drag.current = { x: event.clientX, pointer: event.pointerId };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<HTMLLIElement>) => {
    if (drag.current?.pointer === event.pointerId) setOffset(event.clientX - drag.current.x);
  };
  const onPointerEnd = (event: PointerEvent<HTMLLIElement>) => {
    if (drag.current?.pointer !== event.pointerId) return;
    drag.current = null;
    if (Math.abs(offset) > SWIPE_DISMISS_PX) toastApi.dismiss(toast.id);
    else setOffset(0);
  };

  return (
    <li
      className={`${styles.toast} ${styles[toast.type]} ${offset ? styles.dragging : ""}`}
      style={offset ? { transform: `translateX(${offset}px)`, opacity: Math.max(0.2, 1 - Math.abs(offset) / 200) } : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
    >
      <Icon className={styles.icon} size={20} strokeWidth={2} aria-hidden="true" />
      <p className={styles.message}>{toast.message}</p>
      {toast.link && (
        <Link href={toast.link.href} className={styles.action} onClick={() => toastApi.dismiss(toast.id)}>
          {toast.link.label}
        </Link>
      )}
      {toast.action && (
        <button type="button" className={styles.action} onClick={() => toastApi.act(toast.id)}>
          {toast.action.label}
        </button>
      )}
      <button type="button" className={styles.close} onClick={() => toastApi.dismiss(toast.id)} aria-label="Dismiss notification">
        <X size={16} strokeWidth={2} aria-hidden="true" />
      </button>
    </li>
  );
}
