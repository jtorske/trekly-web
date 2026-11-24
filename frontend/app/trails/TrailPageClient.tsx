"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import HikeLogButton from "@/components/HikeLogButton";
import AlertsChip from "@/components/AlertsChip";
import SaveTrailButton from "@/components/SaveTrailButton";
import ReadinessCard from "@/components/guide/ReadinessCard";
import ui from "@/components/ui.module.css";
import TrailPhoto, { PhotoCredit } from "@/components/TrailPhoto";
import { creditPlace } from "@/lib/trailPhoto";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import { trailHref } from "@/lib/site";
import {
  getTrailCampgrounds,
  type SeasonalCondition,
  type TrailCampgrounds,
  type TrailDetail,
} from "@/lib/trailsApi";
import { formatDegrees, formatTemperature, formatTrailDistance, formatTrailElevation, type UnitSystem } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import CampgroundsSection from "./CampgroundsSection";
import HikedBySection from "./HikedBySection";
import WeatherSection, { useTrailForecast } from "./WeatherSection";
import styles from "./page.module.css";

const SEASON_LABELS: Record<SeasonalCondition["season"], string> = {
  spring: "Spring",
  summer: "Summer",
  fall: "Fall",
  winter: "Winter",
};

const PRECIP_LABELS: Record<NonNullable<SeasonalCondition["precip_likelihood"]>, string> = {
  low: "Low chance of precipitation",
  moderate: "Moderate chance of precipitation",
  high: "High chance of precipitation",
};

function formatClimateZone(zone: string): string {
  const words = zone.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

interface StatItem {
  label: string;
  value: string;
}

function Stat({ label, value }: StatItem) {
  return (
    <div className={styles.stat}>
      <dt className={styles.statLabel}>{label}</dt>
      <dd className={styles.statValue}>{value}</dd>
    </div>
  );
}

function SeasonCard({ condition, units }: { condition: SeasonalCondition; units: UnitSystem }) {
  return (
    <li className={styles.season}>
      <div className={styles.seasonHeader}>
        <h3 className={styles.seasonName}>{SEASON_LABELS[condition.season]}</h3>
        <span className={styles.seasonTemps}>
          {formatDegrees(condition.avg_low_c, units)} / {formatTemperature(condition.avg_high_c, units)}
        </span>
      </div>
      <ul className={styles.seasonFacts}>
        {condition.precip_likelihood && (
          <li>{PRECIP_LABELS[condition.precip_likelihood]}</li>
        )}
        {condition.high_wind && <li>Prone to high winds</li>}
      </ul>
      {condition.notes && <p className={styles.seasonNotes}>{condition.notes}</p>}
    </li>
  );
}

function TrailView({
  trail,
  campgrounds,
  campgroundsFailed,
  saved,
  pending,
  onToggleSave,
  hikeLogs,
}: {
  trail: TrailDetail;
  campgrounds: TrailCampgrounds | null;
  campgroundsFailed: boolean;
  saved: boolean;
  pending: boolean;
  onToggleSave: (trailId: string, makeSaved: boolean) => Promise<void>;
  hikeLogs: ReturnType<typeof useHikeLogs>;
}) {
  const [units] = useUnits();
  const forecast = useTrailForecast(trail);
  const nights = trail.typical_duration_nights;
  const [readinessOpen, setReadinessOpen] = useState(false);
  const hasLocation = trail.latitude != null && trail.longitude != null;

  const stats: StatItem[] = [];
  const distance = formatTrailDistance(trail.distance_km, trail.route_type, units);
  if (distance) stats.push({ label: "Distance", value: distance });
  const gain = formatTrailElevation(trail.elevation_gain_m, units);
  if (gain) stats.push({ label: "Elevation gain", value: gain });
  const highPoint = formatTrailElevation(trail.max_elevation_m, units);
  if (highPoint) stats.push({ label: "High point", value: highPoint });
  if (nights != null) {
    stats.push({ label: "Typical trip", value: tripLengthLabel(nights) });
  }
  stats.push({ label: "Difficulty", value: TERRAIN_LABELS[trail.terrain] });

  return (
    <article className={styles.article}>
      <figure className={styles.photo}>
        <TrailPhoto photo={trail.photo} routeMap={trail.route_map} name={trail.name} variant="hero" />
        {(trail.photo || trail.route_map) && (
          <figcaption className={styles.photoCredit}>
            <PhotoCredit photo={trail.photo} routeMap={trail.route_map} place={creditPlace(trail)} />
          </figcaption>
        )}
      </figure>
      <header className={styles.header}>
        <p className={styles.region}>{trail.region}</p>
        <h1 className={styles.title}>{trail.name}</h1>
        {(campgrounds?.overnight_option || trail.has_watchable_campgrounds) && (
          <div className={styles.tags}>
            {campgrounds?.overnight_option && <span className={styles.overnightTag}>Also doable as an overnight</span>}
            {trail.has_watchable_campgrounds && <AlertsChip size="md" />}
          </div>
        )}
      </header>

      <dl className={styles.stats}>
        {stats.map((stat) => (
          <Stat key={stat.label} {...stat} />
        ))}
      </dl>

      <div className={styles.actions}>
        <div className={styles.actionButtons}>
          <SaveTrailButton
            trailId={trail.id}
            trailName={trail.name}
            saved={saved}
            pending={pending}
            onToggle={onToggleSave}
            returnTo={trailHref(trail)}
          />
          <HikeLogButton
            trailId={trail.id}
            trailName={trail.name}
            retired={trail.retired_at !== null}
            entry={hikeLogs.byTrail.get(trail.id) ?? null}
            loading={hikeLogs.loading}
            onSave={hikeLogs.save}
            onRemove={hikeLogs.remove}
            returnTo={trailHref(trail)}
          />
          {trail.retired_at === null && (
            <button
              type="button"
              className={ui.secondary}
              aria-expanded={readinessOpen}
              onClick={() => setReadinessOpen((open) => !open)}
            >
              Am I ready?
            </button>
          )}
        </div>
        {readinessOpen && <ReadinessCard slug={trail.slug} onClose={() => setReadinessOpen(false)} />}
      </div>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>About this trail</h2>
        {trail.description ? (
          <p className={styles.description}>{trail.description}</p>
        ) : (
          <p className={styles.muted}>We don&apos;t have a description for this trail yet.</p>
        )}
      </section>

      <HikedBySection
        trailId={trail.id}
        trailName={trail.name}
        refreshKey={hikeLogs.byTrail.get(trail.id)?.updated_at ?? "none"}
        hikedByMe={hikeLogs.byTrail.has(trail.id)}
        className={styles.section}
      />

      <CampgroundsSection
        trailId={trail.id}
        trailName={trail.name}
        typicalNights={trail.typical_duration_nights}
        data={campgrounds}
        failed={campgroundsFailed && ((trail.typical_duration_nights ?? 0) >= 1)}
        className={styles.section}
      />

      <WeatherSection
        state={forecast}
        units={units}
        latitude={trail.latitude}
        longitude={trail.longitude}
        provinceCode={trail.province_code}
        countryCode={trail.country_code}
        className={styles.section}
      />

      {(trail.seasonal_conditions.length > 0 || trail.climate_zone) && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Seasonal conditions</h2>
          {trail.climate_zone && (
            <p className={styles.climate}>
              Climate: <strong>{formatClimateZone(trail.climate_zone)}</strong>
            </p>
          )}
          {trail.seasonal_conditions.length > 0 && (
            <ul className={styles.seasons}>
              {trail.seasonal_conditions.map((condition) => (
                <SeasonCard key={condition.season} condition={condition} units={units} />
              ))}
            </ul>
          )}
        </section>
      )}

      {hasLocation && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Location</h2>
          <p className={styles.description}>
            {trail.latitude!.toFixed(4)}, {trail.longitude!.toFixed(4)}{" "}
            <a
              className={styles.inlineLink}
              href={`https://www.openstreetmap.org/?mlat=${trail.latitude}&mlon=${trail.longitude}#map=12/${trail.latitude}/${trail.longitude}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              View on map
            </a>
          </p>
        </section>
      )}
    </article>
  );
}

/**
 * The trail page's interactive half. The trail itself arrives from the
 * server (app/trails/[slug]/page.tsx) so its name, stats, description and
 * photo are in the first HTML; campgrounds, "Hiked by", the forecast and
 * the save / log buttons load here in the browser.
 */
export default function TrailPageClient({ trail, saveParam }: { trail: TrailDetail; saveParam: string | null }) {
  const router = useRouter();
  const id = trail.id;
  const { status: authStatus } = useAuth();
  const savedTrails = useSavedTrails();
  const hikeLogs = useHikeLogs();
  const pendingSave = useRef(false);
  const [campgrounds, setCampgrounds] = useState<{
    id: string;
    data: TrailCampgrounds | null;
    failed: boolean;
  } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    // The page renders without it and the section appears once it arrives.
    getTrailCampgrounds(id, controller.signal)
      .then((data) => setCampgrounds({ id, data, failed: false }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setCampgrounds({ id, data: null, failed: true });
        }
      });
    return () => controller.abort();
  }, [id]);
  const trailCampgrounds = campgrounds?.id === id ? campgrounds : null;

  // Returning from sign-in after clicking "Save trail" as a guest: finish the save.
  useEffect(() => {
    if (saveParam !== id || authStatus !== "signedIn" || savedTrails.loading || pendingSave.current) return;
    pendingSave.current = true;
    const finish = () => router.replace(trailHref(trail), { scroll: false });
    if (savedTrails.savedIds.has(id)) finish();
    else savedTrails.toggle(id, true).catch(() => undefined).finally(finish);
  }, [id, trail, saveParam, authStatus, savedTrails, router]);

  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <Link href="/trail-list" className={styles.backLink}>
          ← Explore trails
        </Link>
        <TrailView
          trail={trail}
          campgrounds={trailCampgrounds?.data ?? null}
          campgroundsFailed={trailCampgrounds?.failed ?? false}
          saved={savedTrails.savedIds.has(trail.id)}
          pending={savedTrails.pending.has(trail.id) || (saveParam === trail.id && authStatus === "signedIn")}
          onToggleSave={savedTrails.toggle}
          hikeLogs={hikeLogs}
        />
      </div>
    </main>
  );
}
