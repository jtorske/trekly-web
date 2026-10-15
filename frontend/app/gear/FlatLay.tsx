"use client";

import type { GearItem } from "@/lib/gearApi";
import { formatWeight, type UnitSystem } from "@/lib/units";
import { PlusMark, Silhouette } from "./silhouettes";
import type { Slot } from "./slots";
import styles from "./FlatLay.module.css";

function itemSubtitle(item: GearItem): string {
  if (item.kind === "custom") return [item.custom_brand, item.custom_model].filter(Boolean).join(" ") || "Custom item";
  return item.variant ? `${item.brand_name} · ${item.variant.name}` : (item.brand_name ?? "");
}

interface Props {
  slots: Slot[];
  bySlot: Map<string, GearItem[]>;
  /** Unfiltered view: empty slots and "add another" are offered. Otherwise missing slots are ghosts. */
  showEmptySlots: boolean;
  units: UnitSystem;
  canEdit: boolean;
  addDisabled: boolean;
  /** Id of an item just added, which plays the snap-into-place animation. */
  snapId: string | null;
  /** Shown over the mat when a filtered view has no main pieces. */
  emptyMessage: string | null;
  onAdd: (slot: Slot) => void;
  onOpen: (item: GearItem) => void;
}

/**
 * The Main setup as a flat-lay "knolling" mat: each core slot has a fixed
 * place sized like the real item, drawn as a line silhouette. Extra items in
 * a slot sit beside the first as smaller silhouettes.
 */
export default function FlatLay({
  slots,
  bySlot,
  showEmptySlots,
  units,
  canEdit,
  addDisabled,
  snapId,
  emptyMessage,
  onAdd,
  onOpen,
}: Props) {
  const filledPiece = (item: GearItem, slot: Slot, mini: boolean) => {
    const name = item.product?.name ?? item.display_name;
    const subtitle = itemSubtitle(item);
    return (
      <button
        key={item.id}
        type="button"
        className={`${styles.piece} ${mini ? styles.mini : ""}`}
        data-state="filled"
        data-snap={item.id === snapId || undefined}
        onClick={() => canEdit && onOpen(item)}
        aria-label={`Edit ${slot.noun}: ${name}`}
      >
        <span className={styles.art}>
          <Silhouette slotKey={slot.key} />
          {item.quantity > 1 && <span className={styles.qty}>×{item.quantity}</span>}
        </span>
        <span className={styles.caption}>
          <span className={styles.name}>{name}</span>
          {subtitle && <span className={styles.brand}>{subtitle}</span>}
          <span className={styles.weight}>
            {item.weight.effective_g != null ? formatWeight(item.weight.effective_g * item.quantity, units) : "Weight unknown"}
          </span>
        </span>
      </button>
    );
  };

  return (
    <div className={styles.wrap}>
      <ul className={styles.mat} data-dimmed={emptyMessage ? true : undefined}>
        {slots.map((slot) => {
          const items = bySlot.get(slot.key) ?? [];

          if (items.length === 0) {
            if (!showEmptySlots) {
              return (
                <li key={slot.key} className={styles.cell} data-slot={slot.key} aria-hidden="true">
                  <span className={styles.ghost}>
                    <span className={styles.art}>
                      <Silhouette slotKey={slot.key} />
                    </span>
                  </span>
                </li>
              );
            }
            return (
              <li key={slot.key} className={styles.cell} data-slot={slot.key}>
                <button
                  type="button"
                  className={styles.piece}
                  data-state="empty"
                  onClick={() => onAdd(slot)}
                  disabled={addDisabled}
                  aria-label={`Add your ${slot.noun}`}
                >
                  <span className={styles.art}>
                    <Silhouette slotKey={slot.key} />
                    <PlusMark className={styles.plus} />
                  </span>
                  <span className={styles.caption}>
                    <span className={styles.label}>{slot.label}</span>
                  </span>
                </button>
              </li>
            );
          }

          const [first, ...extras] = items;
          const offerAnother = showEmptySlots && !slot.single;
          const anotherLabel = `Add another ${slot.noun}`;
          return (
            <li key={slot.key} className={styles.cell} data-slot={slot.key}>
              <div className={styles.main}>
                {filledPiece(first, slot, false)}
                {offerAnother && (
                  <button
                    type="button"
                    className={styles.another}
                    onClick={() => onAdd(slot)}
                    disabled={addDisabled}
                    aria-label={anotherLabel}
                  >
                    <PlusMark className={styles.anotherPlus} />
                    Add another
                  </button>
                )}
              </div>
              {extras.length > 0 && <div className={styles.minis}>{extras.map((item) => filledPiece(item, slot, true))}</div>}
            </li>
          );
        })}
      </ul>
      {emptyMessage && (
        <p className={styles.overlay} role="status">
          {emptyMessage}
        </p>
      )}
    </div>
  );
}
