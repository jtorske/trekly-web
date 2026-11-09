import { refreshMilestones } from "./useMilestones";
import { refreshRank } from "./useRank";

/**
 * After hikes are added, by any entry point ("Mark as hiked", "Add past
 * hikes", onboarding, a GPX import): refresh the shared rank and milestones
 * once, however many were added. The server has already counted them
 * (app/hike_service.py); this brings the profile card, avatar menu and
 * journal up to date.
 *
 * Normally a new milestone gets a toast and a new rank its celebration.
 * `quiet` (onboarding) records them as seen without either, because the
 * finish screen shows one summary instead.
 */
export function refreshAfterHikesAdded({ quiet = false }: { quiet?: boolean } = {}): Promise<void> {
  return Promise.all([refreshRank(quiet ? "onboarding" : "hike-added"), refreshMilestones({ quiet })]).then(() => undefined);
}
