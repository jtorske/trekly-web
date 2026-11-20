/**
 * Where a dropdown goes when it's drawn with `position: fixed` under (or, when
 * there's no room, over) the field it belongs to, so a scrolling column or a
 * card's edge can never clip it. All numbers are viewport pixels.
 */

export interface Rect {
  top: number;
  bottom: number;
  left: number;
  width: number;
}

export interface FloatingBox {
  top?: number;
  bottom?: number;
  left: number;
  width: number;
  maxHeight: number;
}

/** Gap between the field and the dropdown, and from the viewport's edges. */
export const GAP = 6;
export const EDGE = 8;

export function floatingBox(
  field: Rect,
  viewport: { width: number; height: number },
  { minWidth = 320, idealHeight = 352, minBelow = 220, topInset = 0 } = {},
): FloatingBox {
  const width = Math.min(Math.max(field.width, minWidth), viewport.width - EDGE * 2);
  const left = Math.max(EDGE, Math.min(field.left, viewport.width - EDGE - width));
  const below = viewport.height - field.bottom - GAP - EDGE;
  const above = field.top - GAP - EDGE - topInset;
  if (below >= Math.min(minBelow, idealHeight) || below >= above) {
    return { top: field.bottom + GAP, left, width, maxHeight: Math.max(0, Math.min(idealHeight, below)) };
  }
  return { bottom: viewport.height - field.top + GAP, left, width, maxHeight: Math.max(0, Math.min(idealHeight, above)) };
}
