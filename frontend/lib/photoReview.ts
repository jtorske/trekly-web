/**
 * Pure helpers for the trail photo review page (/admin/photos): which trails
 * need a look, and what each review shortcut does.
 */

export interface ReviewItemState {
  trail: { photo?: unknown | null };
  candidates: readonly unknown[];
  /** When the trail's candidates were loaded (ISO); null for none. */
  candidates_loaded_at?: string | null;
  review: { decision: "approved" | "rejected" | "uploaded"; reviewed_at?: string | null } | null;
}

function time(value: string | null | undefined): number {
  const parsed = value ? Date.parse(value) : NaN;
  return Number.isNaN(parsed) ? 0 : parsed;
}

/**
 * "To review": candidates you haven't decided on yet. Either the trail has
 * never been reviewed, or you chose "No photo" before a newer search loaded
 * fresh candidates. Trails with a photo (approved or your own) never show.
 */
export function hasNewCandidates(item: ReviewItemState): boolean {
  if (item.candidates.length === 0 || item.trail.photo) return false;
  if (!item.review) return true;
  return item.review.decision === "rejected" && time(item.candidates_loaded_at) > time(item.review.reviewed_at);
}

/** Nothing usable was found and the trail has no photo: upload your own or keep the topo. */
export function hasNoCandidates(item: ReviewItemState): boolean {
  return item.candidates.length === 0 && !item.trail.photo;
}

export type ReviewShortcut =
  | { kind: "pick"; index: number }
  | { kind: "none" }
  | { kind: "save" }
  | { kind: "move"; by: 1 | -1 };

/** 1–5 pick a candidate, N no photo, Enter approve, arrows next/previous. */
export function reviewShortcut(key: string): ReviewShortcut | null {
  if (/^[1-5]$/.test(key)) return { kind: "pick", index: Number(key) - 1 };
  if (key === "n" || key === "N") return { kind: "none" };
  if (key === "Enter") return { kind: "save" };
  if (key === "ArrowDown" || key === "ArrowRight") return { kind: "move", by: 1 };
  if (key === "ArrowUp" || key === "ArrowLeft") return { kind: "move", by: -1 };
  return null;
}

/**
 * The next active trail, moving `by` from (page, index) through pages of
 * `size` over `total` trails; it stops at the first and the last.
 */
export function moveActive(
  position: { page: number; index: number },
  by: 1 | -1,
  total: number,
  size: number,
): { page: number; index: number } {
  const flat = Math.min(Math.max(position.page * size + position.index + by, 0), Math.max(total - 1, 0));
  return { page: Math.floor(flat / size), index: flat % size };
}
