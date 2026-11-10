"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import MilestoneBadge from "@/components/MilestoneBadge";
import MilestoneCard from "@/components/MilestoneCard";
import { badgeMilestone, milestoneSlug, shortDay, theirEarnedWhen, viewerStanding, type MilestoneBadgeInfo } from "@/lib/milestones";
import { useMilestones } from "@/lib/useMilestones";
import { useUnits } from "@/lib/useUnits";

/**
 * Someone's earned milestone badge that explains itself: the journal's
 * MilestoneCard showing the badge, its name, tier and requirement, and when
 * its owner earned it (unless they hide their dates). A signed-in viewer also
 * sees where they stand on it, with a link to it in their Trail Journal; a
 * secret they haven't earned stays a secret.
 *
 * `children` is what's tapped: the badge art, or its name with variant "text".
 */
export default function MilestoneBadgeCard({
  badge,
  owner,
  mine = false,
  variant = "medal",
  keyboard,
  className,
  children,
}: {
  badge: MilestoneBadgeInfo;
  /** The owner's display name. */
  owner: string;
  /** The badge is the viewer's own. */
  mine?: boolean;
  variant?: "medal" | "text";
  /** false: pointers only, for a second way into the same card. */
  keyboard?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const { milestones } = useMilestones();
  const [units] = useUnits();
  const milestone = badgeMilestone(badge);

  let footer: ReactNode = null;
  if (user && milestones) {
    const standing = mine ? null : viewerStanding(badge.id, milestones, shortDay, units);
    const href = `/journal?section=${encodeURIComponent(milestoneSlug(milestones, badge.id))}`;
    footer = (
      <>
        {standing && <span>{standing.text}</span>}
        {/* A secret the viewer hasn't earned has no page to point at. */}
        {!standing?.secret && <Link href={href}>{mine ? "See it in your Trail Journal" : "Your Trail Journal"}</Link>}
      </>
    );
  }

  return (
    <MilestoneCard
      milestone={milestone}
      units={units}
      variant={variant}
      keyboard={keyboard}
      className={className}
      label={`${badge.title}: ${mine ? "your" : `${owner}'s`} milestone details`}
      badge={{
        art: <MilestoneBadge icon={badge.icon} tier={badge.tier} />,
        status: mine ? "Earned" : `Earned by ${owner}`,
        when: theirEarnedWhen(badge, shortDay),
      }}
      footer={footer}
    >
      {children}
    </MilestoneCard>
  );
}
