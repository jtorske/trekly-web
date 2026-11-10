import { apiFetch } from "./api";
import type { TrailHikers } from "./hikedBy";

/** "Hiked by" for a trail. Signed in, each hiker also says whether you follow them. */
export const getTrailHikers = (trailId: string, signedIn: boolean, signal?: AbortSignal) =>
  apiFetch<TrailHikers>(`/api/trails/${encodeURIComponent(trailId)}/hikers`, { auth: signedIn, signal });
