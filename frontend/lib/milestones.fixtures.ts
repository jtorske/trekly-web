import type { Milestone, Milestones } from "./milestones.ts";

/** Test data shaped like the server's /api/me/milestones answer. */
export function milestone(overrides: Partial<Milestone> = {}): Milestone {
  return {
    id: "first-hike",
    category: "getting-out",
    title: "First steps",
    detail: "Log your first hike",
    goal: 1,
    unit: null,
    tier: "bronze",
    icon: "first-hike",
    secret: false,
    earned: false,
    progress: null,
    ...overrides,
  };
}

export const CATEGORIES = [
  ["getting-out", "Getting out there"],
  ["nights", "Nights out"],
  ["distance", "Distance"],
  ["elevation", "Elevation"],
  ["exploration", "Exploration"],
  ["difficulty", "Difficulty"],
  ["seasons", "Seasons"],
  ["journal", "Journal"],
  ["planning", "Planning and gear"],
  ["secret", "Secret"],
] as const;

export function sample(milestones: Milestone[] = [milestone()], categories = CATEGORIES.map(([id, title]) => ({ id, title }))): Milestones {
  return { categories, milestones, tier_points: { bronze: 10, silver: 25, gold: 50 } };
}
