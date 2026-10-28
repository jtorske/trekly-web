/**
 * Ranks come from points the server computes from hike logs (backend
 * app/points.py, values in app/points_config.py); nothing here scores
 * anything. These are the shapes, the progress label, and when to
 * celebrate a rank-up.
 */

export interface Rank {
  /** 1 (Trailhead Rookie) to 7 (Mountain Legend). */
  level: number;
  title: string;
}

export interface MyRank {
  points: number;
  rank: Rank & { threshold: number };
  /** null at the top rank. */
  next: (Rank & { threshold: number }) | null;
  /** 0–1 from this rank's threshold to the next one's. */
  progress: number;
  breakdown: { trails: number; nights: number; regions: number; milestones: number };
}

export interface RankRules {
  trail_points: Record<"easy" | "moderate" | "difficult" | "extreme", number>;
  points_per_night: number;
  new_region_points: number;
  milestone_points: number;
  ranks: (Rank & { threshold: number })[];
}

/** "120 / 250 points to Switchback Regular", or the total at the top rank. */
export function progressLabel(mine: MyRank): string {
  if (!mine.next) return `${mine.points.toLocaleString()} points · the top rank`;
  return `${mine.points.toLocaleString()} / ${mine.next.threshold.toLocaleString()} points to ${mine.next.title}`;
}

/** Why the rank was re-fetched: only logging a new hike can celebrate. */
export type RankCause = "load" | "hike-added" | "hike-changed";

/**
 * A rank-up is celebrated once, right after logging the hike that earned
 * it: never on a page load, never for an edit or deletion (which can only
 * keep or lower the rank), and never without a known rank to compare with.
 */
export function shouldCelebrate(previous: Rank | null, next: Rank, cause: RankCause): boolean {
  return cause === "hike-added" && previous !== null && next.level > previous.level;
}
