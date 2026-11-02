export type Terrain = "easy" | "moderate" | "difficult" | "extreme";

export const TERRAIN_LABELS: Record<Terrain, string> = {
  easy: "Easy",
  moderate: "Moderate",
  difficult: "Difficult",
  extreme: "Extreme",
};

/** Map marker colours, distinct on a pale map and against each other. */
export const TERRAIN_COLORS: Record<Terrain, string> = {
  easy: "#5b7a29",
  moderate: "#c48a16",
  difficult: "#b4501b",
  extreme: "#253947",
};
