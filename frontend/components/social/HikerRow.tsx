"use client";

import Link from "next/link";
import Avatar from "@/components/Avatar";
import FollowButton from "@/components/FollowButton";
import ProvinceBadge from "@/components/ProvinceBadge";
import RankEmblem from "@/components/RankEmblem";
import { commonTrailsLabel, hikerName, isLimited, type HikerResult } from "@/lib/hikerSearch";
import { publicProfilePath } from "@/lib/profilesApi";
import { province as provinceFor } from "@/lib/provinces";
import styles from "./HikerRow.module.css";

/**
 * One hiker in search results or suggestions: photo, name and @username,
 * then what they show (rank, home province) and what you share ("You've
 * both hiked 3 trails"), and a follow button. A private profile you don't
 * follow shows only its name, username and photo.
 *
 * `reason` replaces the trails-in-common line (suggestions). `compact` is
 * the Activity dropdown and sidebar: smaller, details on one line.
 */
export default function HikerRow({
  hiker,
  reason,
  compact = false,
  onNavigate,
  as: Tag = "li",
  id,
  active = false,
}: {
  hiker: HikerResult;
  reason?: string | null;
  compact?: boolean;
  onNavigate?: () => void;
  as?: "li" | "div";
  id?: string;
  /** Highlighted by the arrow keys in a dropdown. */
  active?: boolean;
}) {
  const name = hikerName(hiker);
  const limited = isLimited(hiker);
  const place = limited ? null : provinceFor(hiker.home_province);
  const note = reason !== undefined ? reason : limited ? null : commonTrailsLabel(hiker.common_trails);
  const rank = limited ? null : hiker.rank;

  return (
    <Tag className={`${styles.row} ${compact ? styles.compact : ""}`} id={id} data-active={active || undefined}>
      <Link href={publicProfilePath(hiker.username)} className={styles.who} onClick={onNavigate}>
        <Avatar path={hiker.avatar_path} name={hiker.display_name ?? hiker.username} email={null} size={compact ? 36 : 44} />
        <span className={styles.text}>
          <span className={styles.name}>{name}</span>
          <span className={styles.handle}>@{hiker.username}</span>
          {(rank || place) && (
            <span className={styles.details}>
              {rank && (
                <span className={styles.detail}>
                  <RankEmblem level={rank.level} className={styles.emblem} />
                  {rank.title}
                </span>
              )}
              {place && (
                <span className={styles.detail}>
                  <ProvinceBadge province={place} decorative className={styles.province} />
                  {place.name}
                </span>
              )}
            </span>
          )}
          {note && <span className={styles.note}>{note}</span>}
        </span>
      </Link>
      <span className={styles.action}>
        <FollowButton username={hiker.username} name={name} state={hiker.follow} isPrivate={hiker.is_private} size="sm" />
      </span>
    </Tag>
  );
}
