"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import HikeLogButton from "@/components/HikeLogButton";
import SaveTrailButton from "@/components/SaveTrailButton";
import ui from "@/components/ui.module.css";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useSavedTrails } from "@/lib/useSavedTrails";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import {
  getTrail,
  getTrailCampgrounds,
  type SeasonalCondition,
  type TrailCampgrounds,
  type TrailDetail,
} from "@/lib/trailsApi";
import { formatDegrees, formatTemperature, formatTrailDistance, formatTrailElevation, type UnitSystem } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import CampgroundsSection from "./CampgroundsSection";
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
  const [units, setUnits] = useUnits();
  const forecast = useTrailForecast(trail.id);
  const nights = trail.typical_duration_nights;
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
  // Only offer mi/ft vs km/m when something on the page converts.
  const hasUnits = Boolean(distance || gain || highPoint) || trail.seasonal_conditions.length > 0 || forecast.status === "ready";

  return (
    <article className={styles.article}>
      <header className={styles.header}>
        <p className={styles.region}>{trail.region}</p>
        <h1 className={styles.title}>{trail.name}</h1>
        {campgrounds?.overnight_option && (
          <div className={styles.tags}>
            <span className={styles.overnightTag}>Also doable as an overnight</span>
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
            returnTo={`/trails?id=${encodeURIComponent(trail.id)}`}
          />
          <HikeLogButton
            trailId={trail.id}
            trailName={trail.name}
            retired={trail.retired_at !== null}
            entry={hikeLogs.byTrail.get(trail.id) ?? null}
            loading={hikeLogs.loading}
            onSave={hikeLogs.save}
            onRemove={hikeLogs.remove}
            returnTo={`/trails?id=${encodeURIComponent(trail.id)}`}
          />
        </div>
        {hasUnits && (
          <div className={ui.segmented} role="group" aria-label="Units">
            <button type="button" aria-pressed={units === "imperial"} onClick={() => setUnits("imperial")}>
              mi/ft
            </button>
            <button type="button" aria-pressed={units === "metric"} onClick={() => setUnits("metric")}>
              km/m
            </button>
          </div>
        )}
      </div>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>About this trail</h2>
        {trail.description ? (
          <p className={styles.description}>{trail.description}</p>
        ) : (
          <p className={styles.muted}>We don&apos;t have a description for this trail yet.</p>
        )}
      </section>

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

function TrailContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = searchParams.get("id");
  const { status: authStatus } = useAuth();
  const savedTrails = useSavedTrails();
  const hikeLogs = useHikeLogs();
  const pendingSave = useRef(false);
  const [result, setResult] = useState<{
    id: string;
    trail: TrailDetail | null;
    failed: boolean;
  } | null>(null);
  const [campgrounds, setCampgrounds] = useState<{
    id: string;
    data: TrailCampgrounds | null;
    failed: boolean;
  } | null>(null);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    getTrail(id, controller.signal)
      .then((trail) => setResult({ id, trail, failed: false }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setResult({ id, trail: null, failed: true });
        }
      });
    // Fetched in parallel; the page renders without it and the section
    // appears once it arrives.
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

  const isLoading = id !== null && result?.id !== id;

  // Returning from sign-in after clicking "Save trail" as a guest: finish the save.
  const saveParam = searchParams.get("save");
  useEffect(() => {
    if (!id || saveParam !== id || authStatus !== "signedIn" || savedTrails.loading || pendingSave.current) return;
    pendingSave.current = true;
    const finish = () => router.replace(`/trails?id=${encodeURIComponent(id)}`, { scroll: false });
    if (savedTrails.savedIds.has(id)) finish();
    else savedTrails.toggle(id, true).catch(() => undefined).finally(finish);
  }, [id, saveParam, authStatus, savedTrails, router]);

  let body;
  if (isLoading) {
    body = <p className={styles.status}>Loading trail…</p>;
  } else if (result?.failed) {
    body = (
      <p className={styles.status}>
        We couldn&apos;t load this trail right now. Check that the trail service
        is running and try again.
      </p>
    );
  } else if (!result?.trail) {
    body = (
      <div className={styles.status}>
        <h1 className={styles.notFoundTitle}>Trail not found</h1>
        <p>This trail doesn&apos;t exist or may have been removed.</p>
        <Link href="/trail-list" className={styles.inlineLink}>
          Browse all trails
        </Link>
      </div>
    );
  } else {
    body = (
      <TrailView
        trail={result.trail}
        campgrounds={trailCampgrounds?.data ?? null}
        campgroundsFailed={trailCampgrounds?.failed ?? false}
        saved={savedTrails.savedIds.has(result.trail.id)}
        pending={savedTrails.pending.has(result.trail.id) || (saveParam === result.trail.id && authStatus === "signedIn")}
        onToggleSave={savedTrails.toggle}
        hikeLogs={hikeLogs}
      />
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <Link href="/trail-list" className={styles.backLink}>
          ← Explore trails
        </Link>
        {body}
      </div>
    </main>
  );
}

export default function TrailPage() {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <TrailContent />
    </Suspense>
  );
}
