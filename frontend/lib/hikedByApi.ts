import { apiFetch } from "./api";
import type { TrailHikers } from "./hikedBy";

/** "Hiked by" for a trail; the same answer for guests and signed-in users. */
export const getTrailHikers = (trailId: string, signal?: AbortSignal) =>
  apiFetch<TrailHikers>(`/api/trails/${encodeURIComponent(trailId)}/hikers`, { signal });
