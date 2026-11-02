"use client";

import { useState } from "react";
import type { GearItem } from "@/lib/gearApi";
import { formatWeight, type UnitSystem } from "@/lib/units";
import { packSummary, type ZoneWeight } from "./baseWeight";
import { PACK_CLASSES } from "./weightConfig";
import styles from "./WeightSummary.module.css";

function percent(part: number, whole: number): string {
  return whole > 0 ? `${Math.round((part / whole) * 100)}%` : "0%";
}

/** "X of 7 main pieces" as a small ring. */
function PiecesRing({ filled, total }: { filled: number; total: number }) {
  const radius = 15;
  const circumference = 2 * Math.PI * radius;
  const share = total > 0 ? filled / total : 0;
  return (
    <div className={styles.pieces}>
      <svg className={styles.ring} viewBox="0 0 36 36" aria-hidden="true" focusable="false">
        <circle className={styles.ringTrack} cx="18" cy="18" r={radius} />
        {filled > 0 && (
          <circle
            className={styles.ringValue}
            cx="18"
            cy="18"
            r={radius}
            strokeDasharray={`${share * circumference} ${circumference}`}
            transform="rotate(-90 18 18)"
          />
        )}
        <text x="18" y="18" className={styles.ringText} dominantBaseline="central" textAnchor="middle">
          {filled}
        </text>
      </svg>
      <span className={styles.piecesLabel}>
        {filled} of {total} main pieces
      </span>
    </div>
  );
}

/** Packed weight by category; the Big Three get their own colours, the rest share a neutral. */
function ZoneBar({ zones, base, units }: { zones: ZoneWeight[]; base: number; units: UnitSystem }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const others = zones.filter((zone) => !zone.bigThree);
  const othersGrams = others.reduce((sum, zone) => sum + zone.grams, 0);
  const tip = zones.find((zone) => zone.slug === hovered);
  const described = zones.map((zone) => `${zone.label} ${formatWeight(zone.grams, units)}`).join(", ");
  return (
    <div className={styles.breakdown}>
      <div className={styles.barWrap} onPointerLeave={() => setHovered(null)}>
        <div className={styles.bar} role="img" aria-label={`Packed weight by category: ${described}`}>
          {zones.map((zone) => (
            <span
              key={zone.slug}
              className={styles.segment}
              data-zone={zone.bigThree ? zone.slug : "other"}
              data-active={hovered === zone.slug || undefined}
              style={{ flexGrow: zone.grams }}
              onPointerEnter={() => setHovered(zone.slug)}
            />
          ))}
        </div>
        {tip && (
          <p className={styles.tip} role="presentation">
            <strong>{tip.label}</strong> {formatWeight(tip.grams, units)} · {percent(tip.grams, base)}
          </p>
        )}
      </div>
      <ul className={styles.legend}>
        {zones
          .filter((zone) => zone.bigThree)
          .map((zone) => (
            <li key={zone.slug}>
              <span className={styles.swatch} data-zone={zone.slug} aria-hidden="true" />
              <span className={styles.legendLabel}>{zone.label}</span>
              <span className={styles.legendValue}>{formatWeight(zone.grams, units)}</span>
            </li>
          ))}
        {others.length > 0 && (
          <li>
            <span className={styles.swatch} data-zone="other" aria-hidden="true" />
            <span className={styles.legendLabel}>Everything else</span>
            <span className={styles.legendValue}>{formatWeight(othersGrams, units)}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

/**
 * The flagship summary above More gear: base weight (packed items only), its
 * class, the Big Three, and how much of the main setup is on the mat.
 */
export default function WeightSummary({
  items,
  units,
  coreFilled,
  coreTotal,
  scopeLabel,
}: {
  /** The gear in view: all of it, or one setup's. */
  items: GearItem[];
  units: UnitSystem;
  coreFilled: number;
  coreTotal: number;
  /** "All my gear" or the setup's name. */
  scopeLabel: string | null;
}) {
  const summary = packSummary(items);
  const extras = [
    summary.wornGrams > 0 && `${formatWeight(summary.wornGrams, units)} worn`,
    summary.consumableGrams > 0 && `${formatWeight(summary.consumableGrams, units)} consumable`,
  ].filter(Boolean);
  const bandIndex = summary.packClass ? PACK_CLASSES.indexOf(summary.packClass) : -1;
  const limit = summary.packClass?.underGrams;
  const classHint = summary.packClass
    ? limit != null
      ? `Base weight under ${formatWeight(limit, units)}`
      : `Base weight of ${formatWeight(PACK_CLASSES[bandIndex - 1].underGrams!, units)} or more`
    : null;

  return (
    <section className={styles.summary} aria-labelledby="weight-summary-title">
      <div className={styles.top}>
        <div className={styles.headline}>
          <h2 id="weight-summary-title" className={styles.eyebrow}>
            Base weight{scopeLabel && <span className={styles.scope}> · {scopeLabel}</span>}
          </h2>
          {items.length === 0 ? (
            <p className={styles.missing}>Add gear to see your base weight</p>
          ) : summary.missingBase > 0 ? (
            <p className={styles.missing}>
              Some items have no weight
              <span className={styles.missingHint}>
                Add a weight to {summary.missingBase} {summary.missingBase === 1 ? "item" : "items"} to see the total.
              </span>
            </p>
          ) : (
            <p className={styles.big}>{formatWeight(summary.baseGrams, units)}</p>
          )}
          {extras.length > 0 && <p className={styles.extras}>Plus {extras.join(" · ")}</p>}
        </div>
        <PiecesRing filled={coreFilled} total={coreTotal} />
      </div>

      {summary.packClass && (
        <p className={styles.classRow}>
          <span className={styles.classBadge} data-class={summary.packClass.key} title={classHint ?? undefined}>
            {summary.packClass.label}
          </span>
          <span className={styles.classHint}>{classHint}</span>
        </p>
      )}

      {summary.zones.length > 0 && (
        <>
          <ZoneBar zones={summary.zones} base={summary.baseGrams} units={units} />
          <p className={styles.bigThree}>
            Big Three: <strong>{formatWeight(summary.bigThreeGrams, units)}</strong>
            {summary.missingBase === 0 && <> · {percent(summary.bigThreeGrams, summary.baseGrams)} of base weight</>}
            {summary.missingBase > 0 && " · known weights only"}
          </p>
        </>
      )}
    </section>
  );
}
