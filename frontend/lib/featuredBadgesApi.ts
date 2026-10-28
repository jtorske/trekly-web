import { apiFetch } from "./api";
import type { FeaturedBadge, FeaturedBadges, MilestoneId } from "./featuredBadges";

type BadgeIn = { trail_id: string } | { milestone: MilestoneId };

export const getFeaturedBadges = (signal?: AbortSignal) => apiFetch<FeaturedBadges>("/api/me/featured-badges", { auth: true, signal });

/** Replace the picks, in order; an empty list goes back to the most recent. */
export const saveFeaturedBadges = (badges: FeaturedBadge[]) =>
  apiFetch<FeaturedBadges>("/api/me/featured-badges", {
    method: "PUT",
    auth: true,
    body: {
      badges: badges.map((badge): BadgeIn => (badge.kind === "trail" ? { trail_id: badge.trail.id } : { milestone: badge.milestone })),
    },
  });
