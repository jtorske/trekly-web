"use client";

import Link from "next/link";
import { BookOpen } from "lucide-react";
import TrailBadge from "@/components/TrailBadge";
import ui from "@/components/ui.module.css";
import { summarizeJournal, type SummaryHike } from "@/lib/journal";
import { formatHikeDate } from "@/lib/publicProfile";
import { formatElevation, formatWholeDistance, type UnitSystem } from "@/lib/units";
import { useTrailCatalogue } from "@/lib/useTrailCatalogue";
import { SectionCard } from "./ProfileShell";
import { EmptyState } from "./sections";
import shell from "./shell.module.css";
import styles from "./JournalTab.module.css";

/**
 * The profile's Journal tab: the Trail Journal in numbers (not the book).
 * The owner passes their own hikes; a visitor's come from the public
 * profile, which has no dates at all when the owner hides them.
 */
export default function JournalTab({
  hikes,
  owner,
  units,
}: {
  /** null while loading. */
  hikes: SummaryHike[] | null;
  owner: boolean;
  units: UnitSystem;
}) {
  const { catalogue, failed } = useTrailCatalogue();

  if (hikes && hikes.length === 0) {
    return (
      <SectionCard id="journal" title="Trail Journal">
        {owner ? (
          <EmptyState icon={BookOpen} title="Your journal is empty" action={{ href: "/trail-list", label: "Explore trails" }}>
            Mark a trail as hiked to start your journal.
          </EmptyState>
        ) : (
          <p className={styles.quiet}>No hikes logged yet.</p>
        )}
      </SectionCard>
    );
  }

  if (failed) {
    return (
      <SectionCard id="journal" title="Trail Journal">
        <p className={ui.error} role="alert">
          The trail catalogue didn&apos;t load, so the journal can&apos;t be summed up. Try again in a moment.
        </p>
      </SectionCard>
    );
  }

  if (!hikes || !catalogue) {
    return (
      <div className={shell.main} aria-busy="true" aria-label="Loading the journal">
        <div className={`${ui.skeleton} ${styles.skeletonStats}`} />
        <div className={`${ui.skeleton} ${styles.skeletonCard}`} />
      </div>
    );
  }

  const summary = summarizeJournal(catalogue, hikes);
  const dated = hikes.every((hike) => hike.hiked_on);
  const stats: { label: string; value: string }[] = [
    { label: "Trails hiked", value: `${summary.hiked} / ${summary.total}` },
    { label: summary.places === 1 ? "Park or region" : "Parks and regions", value: String(summary.places) },
    { label: summary.overnights === 1 ? "Overnight trip" : "Overnight trips", value: String(summary.overnights) },
    { label: summary.nights === 1 ? "Night in the backcountry" : "Nights in the backcountry", value: String(summary.nights) },
  ];
  if (summary.distanceKm !== null) stats.push({ label: "Distance hiked", value: formatWholeDistance(summary.distanceKm, units) });
  if (summary.elevationM !== null) stats.push({ label: "Elevation gained", value: formatElevation(summary.elevationM, units) });

  return (
    <>
      <SectionCard
        id="journal"
        title="Trail Journal"
        action={
          owner && (
            <Link href="/journal" className={ui.secondary}>
              <BookOpen size={16} aria-hidden="true" />
              Open Trail Journal
            </Link>
          )
        }
      >
        <dl className={styles.stats}>
          {stats.map((stat) => (
            <div key={stat.label} className={styles.stat}>
              <dt className={styles.statLabel}>{stat.label}</dt>
              <dd className={styles.statValue}>{stat.value}</dd>
            </div>
          ))}
        </dl>
      </SectionCard>

      <SectionCard id="stamps" title={dated ? "Recent stamps" : "Stamps"}>
        <ul className={styles.stamps}>
          {summary.recent.map(({ hike, colour }) => (
            <li key={hike.trail.id}>
              <Link href={`/trails?id=${encodeURIComponent(hike.trail.id)}`} className={styles.stamp}>
                <TrailBadge name={hike.trail.name} terrain={hike.trail.terrain} colour={colour} hiked className={styles.stampBadge} />
                <span className={styles.stampName}>{hike.trail.name}</span>
                {hike.hiked_on && <span className={styles.stampDate}>{formatHikeDate(hike.hiked_on)}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard id="regions" title="Region progress">
        <ul className={styles.regions}>
          {summary.regions.map((region) => (
            <li key={region.key} className={styles.region}>
              <span className={styles.regionText}>
                <span className={styles.regionName}>{region.title}</span>
                <span className={styles.regionCount}>
                  {region.hiked} / {region.total}
                  <span className={ui.srOnly}> trails hiked</span>
                </span>
              </span>
              <span className={styles.bar} aria-hidden="true">
                <span
                  className={styles.barFill}
                  style={{ width: `${(region.hiked / region.total) * 100}%`, background: region.colour }}
                />
              </span>
            </li>
          ))}
        </ul>
      </SectionCard>
    </>
  );
}
