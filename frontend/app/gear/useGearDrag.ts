"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { GearItem } from "@/lib/gearApi";

/** Pointer travel before a press becomes a drag, so clicks still click. */
const DRAG_THRESHOLD_PX = 6;

export interface DragState {
  item: GearItem;
  /** Pointer position, for the floating card. */
  x: number;
  y: number;
  /** The drop target under the pointer (its data-drop value), if any. */
  over: string | null;
  /** Set while the card flies into the slot it was dropped on. */
  landing: { x: number; y: number } | null;
}

function targetAt(x: number, y: number): HTMLElement | null {
  return document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-drop]") ?? null;
}

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Drag gear between the mat slots and the More gear panel. Drop targets are
 * any element with `data-drop="<placement>"` (slots.ts matPlacement). Mouse
 * and pen only: touch keeps scrolling, and every item's menu has "Move to…"
 * as the keyboard and touch alternative.
 */
export function useGearDrag(onDrop: (item: GearItem, target: string) => void) {
  const [drag, setDrag] = useState<DragState | null>(null);
  const pending = useRef<{ item: GearItem; x: number; y: number } | null>(null);
  const active = useRef(false);
  const onDropRef = useRef(onDrop);
  useEffect(() => {
    onDropRef.current = onDrop;
  }, [onDrop]);

  const finish = useCallback(() => {
    pending.current = null;
    active.current = false;
    document.documentElement.removeAttribute("data-gear-dragging");
  }, []);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const start = pending.current;
      if (!start) return;
      if (!active.current) {
        if (Math.hypot(event.clientX - start.x, event.clientY - start.y) < DRAG_THRESHOLD_PX) return;
        active.current = true;
        document.documentElement.setAttribute("data-gear-dragging", "");
      }
      event.preventDefault();
      const over = targetAt(event.clientX, event.clientY)?.dataset.drop ?? null;
      setDrag({ item: start.item, x: event.clientX, y: event.clientY, over, landing: null });
    };

    const up = (event: PointerEvent) => {
      const start = pending.current;
      const wasDragging = active.current;
      finish();
      if (!start || !wasDragging) return;
      // The release would also click the item under it; swallow that click.
      // (A click only follows when the release lands on the pressed element,
      // and it's dispatched before any timer runs.)
      const swallow = (click: MouseEvent) => click.stopPropagation();
      window.addEventListener("click", swallow, { capture: true, once: true });
      window.setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 0);
      const target = targetAt(event.clientX, event.clientY);
      const placement = target?.dataset.drop;
      if (!target || !placement) {
        setDrag(null);
        return;
      }
      if (reducedMotion()) {
        setDrag(null);
      } else {
        const rect = target.getBoundingClientRect();
        setDrag({
          item: start.item,
          x: event.clientX,
          y: event.clientY,
          over: placement,
          landing: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
        });
        window.setTimeout(() => setDrag(null), 220);
      }
      onDropRef.current(start.item, placement);
    };

    const cancel = () => {
      if (!pending.current) return;
      finish();
      setDrag(null);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape" && active.current) cancel();
    };

    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key);
    window.addEventListener("blur", cancel);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key);
      window.removeEventListener("blur", cancel);
    };
  }, [finish]);

  /** Spread onto an item's element to make it draggable. */
  const sourceProps = useCallback(
    (item: GearItem) => ({
      onPointerDown: (event: ReactPointerEvent) => {
        if (event.button !== 0 || event.pointerType === "touch") return;
        pending.current = { item, x: event.clientX, y: event.clientY };
      },
      // No native HTML drag of the button or its image.
      onDragStart: (event: React.DragEvent) => event.preventDefault(),
      "data-dragging": drag?.item.id === item.id && !drag.landing ? true : undefined,
    }),
    [drag],
  );

  return { drag, sourceProps };
}
