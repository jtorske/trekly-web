"use client";

import Link from "next/link";
import ui from "@/components/ui.module.css";
import SaveTrailButton from "@/components/SaveTrailButton";
import GearList from "@/app/gear/GearList";
import { summarize } from "@/app/gear/useMyGear";
import { slotForItem, zoneCoverage } from "@/app/gear/slots";
import GearThumb from "@/components/GearThumb";
import type { GearSetup } from "@/lib/setupsApi";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { tripLengthLabel } from "@/lib/tripLength";
import type { SavedTrail } from "@/lib/accountApi";
import type { GearItem } from "@/lib/gearApi";
import { formatWeight, metersToFeet, type UnitSystem } from "@/lib/units";
import styles from "./page.module.css";

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: { href: string; label: string };
}) {
  return (
    <div className={styles.empty}>
      <h3 className={styles.emptyTitle}>{title}</h3>
      <p>{children}</p>
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

export function SavedTrailList({ data, limit }: { data: SavedData; limit?: number }) {
  if (data.loading) return <ListSkeleton />;
  if (data.error) return <SectionError message={data.error} onRetry={data.reload} />;
  if (data.saved.length === 0) {
    return (
      <EmptyState title="No saved trails yet" action={{ href: "/trail-list", label: "Explore trails" }}>
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
                trail.elevation_gain_m != null ? `${metersToFeet(trail.elevation_gain_m).toLocaleString()} ft gain` : null,
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
      <EmptyState title="Your gear mat is empty" action={{ href: "/gear", label: "Add your first piece of gear" }}>
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

export function TripsSection() {
  return (
    <EmptyState title="Trips aren't saved to your account yet" action={{ href: "/trail-list", label: "Explore trails" }}>
      When saved trips arrive, they&apos;ll appear here. Your Gear inventory is separate: it&apos;s everything
      you own, not what you pack for one trip.
    </EmptyState>
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
      <EmptyState title="No setups yet" action={{ href: "/gear", label: "Create a setup" }}>
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
                  productImage={item.product?.image}
                  photoPath={item.image_path}
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
