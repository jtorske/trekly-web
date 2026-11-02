"use client";

import { useMilestones } from "@/lib/useMilestones";

/**
 * Keeps the signed-in user's milestones loaded on every page, so a milestone
 * earned anywhere (or by an alert overnight) gets its toast. Renders nothing;
 * mounted once in the root layout.
 */
export default function MilestoneWatcher() {
  useMilestones();
  return null;
}
