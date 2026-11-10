"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Mountain } from "lucide-react";
import Avatar from "@/components/Avatar";
import MilestoneBadge from "@/components/MilestoneBadge";
import RankEmblem from "@/components/RankEmblem";
import StreakFlame from "@/components/StreakFlame";
import TrailPhoto from "@/components/TrailPhoto";
import ui from "@/components/ui.module.css";
import { latestEarned, type TrendingTrail } from "@/lib/activity";
import { getTrending } from "@/lib/activityApi";
import type { Profile } from "@/lib/accountApi";
import { categorySlug, earnedCount, earnedWhen } from "@/lib/milestones";
import { formatHikeDate } from "@/lib/publicProfile";
import { progressLabel } from "@/lib/rank";
import { useMilestones } from "@/lib/useMilestones";
import { useRank } from "@/lib/useRank";
import { useStreak } from "@/lib/useStreak";
import { showsStreak, streakLabel } from "@/lib/visitStreak";
import styles from "./activity.module.css";

/**
 * The signed-in hiker at a glance: avatar, name, rank with its progress,
 * streak, trails hiked and milestones, and a big "Log a hike". Guests get
 * an invitation instead.
 */
export function ProfileCard({
  profile,
  trailsHiked,
  signedIn,
  signInHref,
  onLogHike,
}: {
  profile: Profile | null;
  trailsHiked: number | null;
  signedIn: boolean;
  signInHref: string;
  onLogHike: () => void;
}) {
  const { rank } = useRank();
  const { streak } = useStreak();
  const { milestones } = useMilestones();

  if (!signedIn) {
    return (
      <section className={styles.sideCard} aria-label="Join Trekly">
        <Mountain size={28} aria-hidden="true" className={styles.composerIcon} />
        <h2 className={styles.sideTitle}>Hike, stamp, share</h2>
        <p className={styles.sideText}>Log the trails you hike, earn badges and ranks, and cheer on other hikers.</p>
        <Link href={signInHref} className={`${ui.primary} ${styles.logButton}`}>
          Sign in
        </Link>
        <Link href="/signup" className={`${ui.secondary} ${styles.logButton}`}>
          Create an account
        </Link>
      </section>
    );
  }

  const name = profile?.display_name?.trim() || (profile?.username ? `@${profile.username}` : "You");
  return (
    <section className={styles.sideCard} aria-label="Your profile">
      <Link href="/profile" className={styles.meHead}>
        <Avatar path={profile?.avatar_path} name={profile?.display_name ?? profile?.username} email={profile?.email ?? null} size={56} />
        <span className={styles.who}>
          <span className={styles.meName}>{name}</span>
          {profile?.username && <span className={styles.meta}>@{profile.username}</span>}
        </span>
      </Link>

      {rank ? (
        <div className={styles.meRank}>
          <RankEmblem level={rank.rank.level} className={styles.meEmblem} />
          <div className={styles.meRankText}>
            <span className={styles.meRankTitle}>{rank.rank.title}</span>
            <span
              className={styles.bar}
              role="progressbar"
              aria-label={progressLabel(rank)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(rank.progress * 100)}
            >
              <span className={styles.barFill} style={{ width: `${rank.progress * 100}%` }} />
            </span>
            <span className={styles.meRankNext}>{progressLabel(rank)}</span>
          </div>
        </div>
      ) : (
        <div className={`${ui.skeleton} ${styles.meRankSkeleton}`} />
      )}

      <dl className={styles.stats}>
        <div>
          <dt>Trails hiked</dt>
          <dd>{trailsHiked ?? "–"}</dd>
        </div>
        <div>
          <dt>Milestones</dt>
          <dd>{milestones ? earnedCount(milestones) : "–"}</dd>
        </div>
        <div>
          <dt>Streak</dt>
          <dd className={styles.streak}>
            {showsStreak(streak) ? (
              <>
                <StreakFlame size={15} />
                <span aria-label={streakLabel(streak.current)}>{streak.current}d</span>
              </>
            ) : (
              "–"
            )}
          </dd>
        </div>
      </dl>

      <button type="button" className={`${ui.primary} ${styles.logButton}`} onClick={onLogHike}>
        <Mountain size={18} aria-hidden="true" />
        Log a hike
      </button>
    </section>
  );
}

/** Trails most logged or saved this week, with thumbnails; popular ones fill a quiet week. */
export function TrendingTrails() {
  const [trails, setTrails] = useState<TrendingTrail[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getTrending(controller.signal)
      .then((body) => setTrails(body.trails))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, []);

  if (failed || (trails && trails.length === 0)) return null;
  const quiet = trails !== null && trails.every((item) => !item.this_week);
  return (
    <section className={styles.sideCard} aria-labelledby="trending-title">
      <h2 id="trending-title" className={styles.sideTitle}>
        {quiet ? "Popular trails" : "Trending trails this week"}
      </h2>
      {trails === null ? (
        <ul className={styles.trending} aria-busy="true">
          {[0, 1, 2].map((n) => (
            <li key={n} className={`${ui.skeleton} ${styles.trendingSkeleton}`} />
          ))}
        </ul>
      ) : (
        <ol className={styles.trending}>
          {trails.map(({ trail, this_week }) => (
            <li key={trail.id}>
              <Link href={`/trails?id=${encodeURIComponent(trail.id)}`} className={styles.trendingRow}>
                <span className={styles.trendingThumb}>
                  <TrailPhoto photo={trail.photo} name={trail.name} variant="thumb" mini />
                </span>
                <span className={styles.pickedText}>
                  <span className={styles.trendingName}>{trail.name}</span>
                  <span className={styles.trailMeta}>
                    {trail.park_name ?? trail.region}
                    {!quiet && !this_week && " · popular"}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** The viewer's latest milestone, linking to its page in the journal. */
export function RecentlyEarned() {
  const { milestones } = useMilestones();
  const latest = milestones ? latestEarned(milestones.milestones) : null;
  if (!milestones || !latest || !latest.tier) return null;
  const when = earnedWhen(latest, formatHikeDate);
  return (
    <section className={styles.sideCard} aria-labelledby="earned-title">
      <h2 id="earned-title" className={styles.sideTitle}>
        Recently earned
      </h2>
      <Link href={`/journal?section=${categorySlug(milestones, latest.category)}`} className={styles.recent}>
        <MilestoneBadge icon={latest.icon} tier={latest.tier} className={styles.badgeLarge} />
        <span className={styles.pickedText}>
          <span className={styles.trendingName}>{latest.title}</span>
          {when && <span className={styles.trailMeta}>{when}</span>}
        </span>
      </Link>
    </section>
  );
}

/**
 * "Hikers you might know": the slot for suggestions once following exists.
 * There's nothing to suggest from yet, so it renders nothing.
 */
export function HikersYouMightKnow() {
  return null;
}
