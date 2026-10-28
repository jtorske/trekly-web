"use client";

import Link from "next/link";
import { Backpack, Bookmark, Layers, Tent, type LucideIcon } from "lucide-react";
import ui from "@/components/ui.module.css";
import SaveTrailButton from "@/components/SaveTrailButton";
import GearList from "@/app/gear/GearList";
import { summarize } from "@/app/gear/useMyGear";
import { slotForItem, zoneCoverage } from "@/app/gear/slots";
import GearThumb from "@/components/GearThumb";
import { matImage } from "@/lib/gearImage";
import type { GearSetup } from "@/lib/setupsApi";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import type { SavedTrail } from "@/lib/accountApi";
import type { GearItem } from "@/lib/gearApi";
import { splitPlans } from "@/lib/planDraft";
import type { TripPlanSummary } from "@/lib/plansApi";
import { formatStay, localToday } from "@/lib/stay";
import { formatTrailElevation, formatWeight, type UnitSystem } from "@/lib/units";
import styles from "./page.module.css";

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
  action?: { href: string; label: string };
}) {
  return (
    <div className={styles.empty}>
      <span className={styles.emptyIcon} aria-hidden="true">
        <Icon size={24} />
      </span>
      <h3 className={styles.emptyTitle}>{title}</h3>
      <p className={styles.emptyText}>{children}</p>
      {action && (
        <Link href={action.href} className={ui.primary}>
          {action.label}
        </Link>
      )}
    </div>
  );
}

function SectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <p className={ui.error} role="alert">
      {message}{" "}
      <button type="button" className={ui.ghost} onClick={onRetry}>
        Try again
      </button>
    </p>
  );
}

function ListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className={styles.skeletonList} aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className={`${ui.skeleton} ${styles.skeletonRow}`} />
      ))}
    </div>
  );
}

export interface GearData {
  status: "signedOut" | "loading" | "ready" | "error";
  items: GearItem[];
  error: string | null;
  reload: () => void;
}

export interface SavedData {
  loading: boolean;
  error: string | null;
  saved: SavedTrail[];
  pending: Set<string>;
  toggle: (trailId: string, makeSaved: boolean) => Promise<void>;
  reload: () => void;
}

function gainLabel(meters: number | null, units: UnitSystem): string | null {
  const gain = formatTrailElevation(meters, units);
  return gain ? `${gain} gain` : null;
}

export function SavedTrailList({ data, units, limit }: { data: SavedData; units: UnitSystem; limit?: number }) {
  if (data.loading) return <ListSkeleton />;
  if (data.error) return <SectionError message={data.error} onRetry={data.reload} />;
  if (data.saved.length === 0) {
    return (
      <EmptyState icon={Bookmark} title="No saved trails yet" action={{ href: "/trail-list", label: "Explore trails" }}>
        Bookmark trails you&apos;d like to hike and they&apos;ll collect here. Saving a trail doesn&apos;t mark
        it as hiked or planned.
      </EmptyState>
    );
  }
  const shown = limit ? data.saved.slice(0, limit) : data.saved;
  return (
    <ul className={styles.trails}>
      {shown.map(({ trail, saved_at }) => (
        <li key={trail.id} className={styles.trailRow}>
          <Link href={`/trails?id=${encodeURIComponent(trail.id)}`} className={styles.trailLink}>
            <span className={styles.trailName}>{trail.name}</span>
            <span className={styles.trailMeta}>
              {[
                trail.region,
                TERRAIN_LABELS[trail.terrain],
                trail.typical_duration_nights != null ? tripLengthLabel(trail.typical_duration_nights) : null,
                gainLabel(trail.elevation_gain_m, units),
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
            <span className={styles.trailSaved}>Saved {new Date(saved_at).toLocaleDateString()}</span>
          </Link>
          <SaveTrailButton
            trailId={trail.id}
            trailName={trail.name}
            saved
            pending={data.pending.has(trail.id)}
            onToggle={data.toggle}
            returnTo="/profile?tab=trails"
            compact
          />
        </li>
      ))}
    </ul>
  );
}

export function GearSection({ gear, units, limit }: { gear: GearData; units: UnitSystem; limit?: number }) {
  if (gear.status === "loading") return <ListSkeleton />;
  if (gear.status === "error") return <SectionError message={gear.error ?? "Couldn't load your gear."} onRetry={gear.reload} />;
  if (gear.items.length === 0) {
    return (
      <EmptyState icon={Backpack} title="Your gear mat is empty" action={{ href: "/gear", label: "Add your first piece of gear" }}>
        Add the equipment you own — from the catalogue or as custom items — and it&apos;ll show up here and on
        your Gear mat.
      </EmptyState>
    );
  }
  const items = limit
    ? [...gear.items].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, limit)
    : gear.items;
  const { knownGrams, missing, quantity } = summarize(gear.items);
  const coverage = zoneCoverage(gear.items);
  return (
    <>
      {!limit && (
        <p className={ui.hint}>
          {quantity} {quantity === 1 ? "item" : "items"} across {coverage.filled} of {coverage.total} categories ·{" "}
          {formatWeight(knownGrams, units)} known weight
          {missing > 0 && ` (${missing} without a weight)`}. This is everything you own, not a trip packing list.
        </p>
      )}
      <GearList items={items} units={units} compact={Boolean(limit)} />
    </>
  );
}

function TripCard({ plan }: { plan: TripPlanSummary }) {
  return (
    <li>
      <Link href={`/plans?id=${encodeURIComponent(plan.id)}`} className={styles.tripCard}>
        <span className={styles.tripTrail}>{plan.title ?? plan.trail.name}</span>
        {plan.title && <span className={styles.tripMeta}>{plan.trail.name}</span>}
        <span className={styles.tripMeta}>{formatStay(plan.start_date, plan.nights)}</span>
        <span className={styles.tripBooked}>
          {plan.booked_nights} of {plan.nights} {plan.nights === 1 ? "night" : "nights"} booked
        </span>
      </Link>
    </li>
  );
}

/** Upcoming plans soonest first; a plan moves to Past the day after its last night. */
export function TripsSection({
  data,
}: {
  data: { loading: boolean; error: string | null; plans: TripPlanSummary[]; reload: () => void };
}) {
  if (data.loading) return <ListSkeleton rows={2} />;
  if (data.error) return <SectionError message={data.error} onRetry={data.reload} />;
  if (data.plans.length === 0) {
    return (
      <EmptyState icon={Tent} title="No trip plans yet" action={{ href: "/trail-list", label: "Explore trails" }}>
        Open an overnight trail and choose &ldquo;Plan this trip&rdquo; to lay out each night, your gear and what
        you&apos;ve booked.
      </EmptyState>
    );
  }
  const { upcoming, past } = splitPlans(data.plans, localToday());
  return (
    <>
      {upcoming.length > 0 ? (
        <ul className={styles.trips}>
          {upcoming.map((plan) => (
            <TripCard key={plan.id} plan={plan} />
          ))}
        </ul>
      ) : (
        <p className={styles.tripsNone}>No upcoming trips.</p>
      )}
      {past.length > 0 && (
        <>
          <h3 className={styles.tripsPastTitle}>Past</h3>
          <ul className={`${styles.trips} ${styles.tripsPast}`}>
            {past.map((plan) => (
              <TripCard key={plan.id} plan={plan} />
            ))}
          </ul>
        </>
      )}
    </>
  );
}

export function SetupsSection({
  data,
  units,
}: {
  data: { loading: boolean; error: string | null; setups: GearSetup[]; reload: () => void };
  units: UnitSystem;
}) {
  if (data.loading) return <ListSkeleton rows={2} />;
  if (data.error) return <SectionError message={data.error} onRetry={data.reload} />;
  if (data.setups.length === 0) {
    return (
      <EmptyState icon={Layers} title="No setups yet" action={{ href: "/gear", label: "Create a setup" }}>
        Group the gear you carry together — like &ldquo;Ultralight 2-Night Kit&rdquo; — to see each kit at a glance.
      </EmptyState>
    );
  }
  return (
    <ul className={styles.setups}>
      {data.setups.map((setup) => (
        <li key={setup.id}>
          <Link href={`/gear?setup=${encodeURIComponent(setup.id)}`} className={styles.setupCard}>
            <span className={styles.setupThumbs} aria-hidden="true">
              {setup.items.slice(0, 4).map((item) => (
                <GearThumb
                  key={item.id}
                  icon={slotForItem(item).icon}
                  productImage={matImage(item)}
                  alt=""
                  size="sm"
                />
              ))}
            </span>
            <span className={styles.setupName}>{setup.name}</span>
            <span className={styles.trailMeta}>
              {setup.item_count} {setup.item_count === 1 ? "item" : "items"} · {formatWeight(setup.known_weight_g, units)}
              {setup.items_missing_weight > 0 && " known"}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
