"use client";

import { useEffect, useId, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { badgeText } from "@/lib/notifications";
import NotificationsPanel from "./NotificationsPanel";
import styles from "./NotificationBell.module.css";

/**
 * The header's bell (900px and up): the unread count as a badge, and the
 * notification list in a dropdown. Escape, a click outside or navigating
 * closes it. Phones reach the list from the menu instead.
 */
export default function NotificationBell({ unread }: { unread: number | null }) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const pathname = usePathname();
  const badge = badgeText(unread ?? 0);

  useEffect(() => {
    queueMicrotask(() => setOpen(false));
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = badge ? `Notifications, ${unread} unread` : "Notifications";
  return (
    <div ref={wrapper} className={styles.wrapper}>
      <button
        ref={trigger}
        type="button"
        className={styles.bell}
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={22} aria-hidden="true" />
        {badge && (
          <span className={styles.badge} aria-hidden="true">
            {badge}
          </span>
        )}
      </button>
      {open && (
        <div id={panelId} className={styles.card} role="dialog" aria-label="Notifications">
          <NotificationsPanel variant="dropdown" onNavigate={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}
