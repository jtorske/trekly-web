import { apiFetch } from "./api";
import type { Milestones } from "./milestones";

/** The signed-in user's milestones, earned or not (backend app/routers/me_milestones.py). */
export const getMyMilestones = (signal?: AbortSignal) => apiFetch<Milestones>("/api/me/milestones", { auth: true, signal });
