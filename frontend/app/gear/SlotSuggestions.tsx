"use client";

import { useEffect, useState } from "react";
import GearThumb from "@/components/GearThumb";
import { popularProducts, type ProductSummary } from "@/lib/gearApi";
import { formatWeight, type UnitSystem } from "@/lib/units";
import type { Slot } from "./slots";
import styles from "./FlatLay.module.css";

/** Extra results fetched so owned products can be skipped and still leave 3. */
const FETCH = 8;
const SHOW = 3;

// One request per slot per page visit; the catalogue barely changes.
const cache = new Map<string, Promise<ProductSummary[]>>();

function load(slot: Slot): Promise<ProductSummary[]> {
  let request = cache.get(slot.key);
  if (!request) {
    request = popularProducts(slot.categories, FETCH);
    request.catch(() => cache.delete(slot.key));
    cache.set(slot.key, request);
  }
  return request;
}

function weightOf(product: ProductSummary, units: UnitSystem): string | null {
  if (product.weight_g != null) return formatWeight(product.weight_g, units);
  if (product.weight_range_g) return `from ${formatWeight(product.weight_range_g[0], units)}`;
  return null;
}

/**
 * Popular picks for an empty mat slot: the most owned catalogue products in
 * its categories, then the lightest, skipping any the user already owns.
 */
export default function SlotSuggestions({
  slot,
  owned,
  units,
  onAdd,
  onBrowse,
}: {
  slot: Slot;
  owned: Map<string, number>;
  units: UnitSystem;
  onAdd: (product: ProductSummary) => void;
  onBrowse: () => void;
}) {
  const [state, setState] = useState<{ key: string; items: ProductSummary[] | null; failed: boolean }>({
    key: slot.key,
    items: null,
    failed: false,
  });

  useEffect(() => {
    let live = true;
    load(slot)
      .then((items) => live && setState({ key: slot.key, items, failed: false }))
      .catch(() => live && setState({ key: slot.key, items: [], failed: true }));
    return () => {
      live = false;
    };
  }, [slot]);

  const items = state.key === slot.key ? state.items : null;
  const picks = (items ?? []).filter((product) => !owned.has(product.id)).slice(0, SHOW);

  return (
    <div className={styles.card} data-kind="suggest" role="group" aria-label={`Popular ${slot.noun} picks`}>
      <p className={styles.cardEyebrow}>Popular picks</p>
      {items == null ? (
        <p className={styles.cardQuiet}>Loading…</p>
      ) : picks.length === 0 ? (
        <p className={styles.cardQuiet}>{state.failed ? "Couldn't load suggestions." : "Browse the catalogue to choose one."}</p>
      ) : (
        <ul className={styles.picks}>
          {picks.map((product) => {
            const weight = weightOf(product, units);
            return (
              <li key={product.id} className={styles.pick}>
                <GearThumb icon={slot.icon} productImage={product.image} alt="" size="sm" />
                <span className={styles.pickBody}>
                  <span className={styles.pickName}>{product.name}</span>
                  <span className={styles.pickMeta}>
                    {product.brand.name}
                    {weight && ` · ${weight}`}
                  </span>
                </span>
                <button
                  type="button"
                  className={styles.pickAdd}
                  onClick={() => onAdd(product)}
                  aria-label={`Add ${product.display_name}`}
                >
                  Add
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <button type="button" className={styles.cardLink} onClick={onBrowse}>
        Browse the catalogue
      </button>
    </div>
  );
}
