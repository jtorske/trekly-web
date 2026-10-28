/**
 * Rank: how many trails someone has logged in their Trail Journal. Mirrors
 * rank_for in backend/app/privacy.py, which ranks public profiles; this one
 * lets owners see their own rank even when it's hidden from visitors.
 */
const RANKS = [
  [50, "Trail Legend"],
  [25, "Backcountry Veteran"],
  [10, "Pathfinder"],
  [3, "Trail Regular"],
  [1, "Day Tripper"],
  [0, "Trailhead"],
] as const;

export interface Rank {
  /** 1 (Trailhead) to 6 (Trail Legend). */
  level: number;
  title: string;
}

export function rankFor(hikes: number): Rank {
  const index = RANKS.findIndex(([threshold]) => hikes >= threshold);
  const at = index === -1 ? RANKS.length - 1 : index;
  return { level: RANKS.length - at, title: RANKS[at][1] };
}
