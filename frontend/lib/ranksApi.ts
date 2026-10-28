import { apiFetch } from "./api";
import type { MyRank, RankRules } from "./rank";

/** The signed-in user's points and rank (computed by the server from their hike logs). */
export const getMyRank = (signal?: AbortSignal) => apiFetch<MyRank>("/api/me/rank", { auth: true, signal });

/** How ranks work: the point values and thresholds (backend app/points_config.py). */
export const getRankRules = (signal?: AbortSignal) => apiFetch<RankRules>("/api/ranks", { signal });
