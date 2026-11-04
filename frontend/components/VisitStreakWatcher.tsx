"use client";

import { useStreak } from "@/lib/useStreak";

/**
 * Records the signed-in user's visit once per app load, on whichever page
 * they land (useStreak does the once-a-day check). Renders nothing; mounted
 * once in the root layout.
 */
export default function VisitStreakWatcher() {
  useStreak();
  return null;
}
