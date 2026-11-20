"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";
import styles from "./MoreMenu.module.css";

export interface MoreMenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  /** Drawn in the warning colour (Delete). */
  danger?: boolean;
}

/**
 * A "⋯" button that opens a small menu of actions (a post's Edit / Delete,
 * a comment's Edit / Delete / Report). Keyboard: Enter or Space opens it on
 * the first item, arrows move, Home/End jump, Escape closes and returns focus,
 * Tab closes. A click outside closes it.
 */
export default function MoreMenu({ label, items, size = 18 }: { label: string; items: MoreMenuItem[]; size?: number }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const away = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menu.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  const close = (focus: boolean) => {
    setOpen(false);
    if (focus) button.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const all = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const at = all.indexOf(document.activeElement as HTMLElement);
    const move = (next: number) => {
      event.preventDefault();
      all[(next + all.length) % all.length]?.focus();
    };
    if (event.key === "ArrowDown") move(at + 1);
    else if (event.key === "ArrowUp") move(at - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(all.length - 1);
    else if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "Tab") close(false);
  };

  if (items.length === 0) return null;
  return (
    <span className={styles.wrap}>
      <button
        ref={button}
        type="button"
        className={styles.trigger}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
      >
        <MoreHorizontal size={size} aria-hidden="true" />
      </button>
      {open && (
        <div ref={menu} id={id} role="menu" aria-label={label} className={styles.menu} onKeyDown={onKeyDown}>
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              tabIndex={-1}
              className={`${styles.item} ${item.danger ? styles.danger : ""}`}
              onClick={() => {
                close(true);
                item.onSelect();
              }}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
