import { apiFetch } from "./api";
import type { Nudge } from "./nudges";

/** The nudges to show this user now (app/nudges.py decides). Never changes a setting. */
export const getNudges = (signal?: AbortSignal) =>
  apiFetch<{ active: Nudge[] }>("/api/me/nudges", { auth: true, signal });

/** Puts a nudge away for good, on every device. Never changes a setting. */
export const dismissNudge = (nudge: Nudge) =>
  apiFetch<void>(`/api/me/nudges/${nudge}/dismissed`, { method: "PUT", auth: true });
