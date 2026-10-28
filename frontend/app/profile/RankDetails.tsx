"use client";

import { useEffect, useState } from "react";
import Dialog from "@/components/Dialog";
import RankEmblem from "@/components/RankEmblem";
import ui from "@/components/ui.module.css";
import { progressLabel, type MyRank, type RankRules } from "@/lib/rank";
import { getRankRules } from "@/lib/ranksApi";
import styles from "./RankDetails.module.css";

/** The owner's progress to the next rank, and how ranks work. Visitors never get points. */
export function RankProgress({ mine }: { mine: MyRank }) {
  const [explaining, setExplaining] = useState(false);
  const label = progressLabel(mine);
  return (
    <div className={styles.progress}>
      <span
        className={styles.bar}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(mine.progress * 100)}
      >
        <span className={styles.fill} style={{ width: `${mine.progress * 100}%` }} />
      </span>
      <span className={styles.label}>{label}</span>
      <button type="button" className={styles.how} onClick={() => setExplaining(true)}>
        How ranks work
      </button>
      {explaining && <RankRulesDialog mine={mine} onClose={() => setExplaining(false)} />}
    </div>
  );
}

function RankRulesDialog({ mine, onClose }: { mine: MyRank; onClose: () => void }) {
  const [rules, setRules] = useState<RankRules | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getRankRules(controller.signal)
      .then(setRules)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, []);

  return (
    <Dialog title="How ranks work" subtitle="You earn points for the hikes in your Trail Journal." onClose={onClose} size="sm">
      {failed && (
        <p className={ui.error} role="alert">
          The rules didn&apos;t load. Try again in a moment.
        </p>
      )}
      {!rules && !failed && <div className={`${ui.skeleton} ${styles.skeleton}`} aria-label="Loading" />}
      {rules && (
        <div className={styles.rules}>
          <section>
            <h3 className={styles.heading}>Points</h3>
            <ul className={styles.list}>
              <li>
                Each trail you hike: easy {rules.trail_points.easy}, moderate {rules.trail_points.moderate}, difficult{" "}
                {rules.trail_points.difficult}, extreme {rules.trail_points.extreme}
              </li>
              <li>Overnight trips: +{rules.points_per_night} a night</li>
              <li>Your first trail in each new park or region: +{rules.new_region_points}</li>
              <li>Each milestone badge: +{rules.milestone_points}</li>
            </ul>
          </section>
          <section>
            <h3 className={styles.heading}>Your points</h3>
            <dl className={styles.breakdown}>
              <dt>Trails</dt>
              <dd>{mine.breakdown.trails}</dd>
              <dt>Nights</dt>
              <dd>{mine.breakdown.nights}</dd>
              <dt>New parks and regions</dt>
              <dd>{mine.breakdown.regions}</dd>
              <dt>Milestones</dt>
              <dd>{mine.breakdown.milestones}</dd>
              <dt className={styles.total}>Total</dt>
              <dd className={styles.total}>{mine.points}</dd>
            </dl>
          </section>
          <section>
            <h3 className={styles.heading}>Ranks</h3>
            <ol className={styles.ranks}>
              {rules.ranks.map((rank) => (
                <li key={rank.level} className={rank.level === mine.rank.level ? styles.current : undefined}>
                  <RankEmblem level={rank.level} className={styles.rankEmblem} />
                  <span className={styles.rankName}>{rank.title}</span>
                  <span className={styles.rankPoints}>{rank.threshold.toLocaleString()}+</span>
                  {rank.level === mine.rank.level && <span className={ui.srOnly}>(your rank)</span>}
                </li>
              ))}
            </ol>
          </section>
          <p className={styles.footnote}>
            Distance and elevation don&apos;t count yet, since many trails are missing them. Deleting a hike takes its points
            away again. Visitors see only your rank&apos;s name and emblem, and only if you show your rank.
          </p>
        </div>
      )}
    </Dialog>
  );
}
