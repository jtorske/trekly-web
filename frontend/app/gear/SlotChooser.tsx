"use client";

import Dialog from "@/components/Dialog";
import type { GearItem } from "@/lib/gearApi";
import { GearIcon } from "./icons";
import { CORE_SLOTS, MORE_GEAR, MORE_ZONES, matPlacement, type Slot } from "./slots";
import styles from "./SlotChooser.module.css";

/**
 * "Move to…": the keyboard and touch alternative to dragging. Lists the mat
 * slots plus More gear; the item's current place is marked and disabled.
 */
export function MoveDialog({
  item,
  onMove,
  onClose,
}: {
  item: GearItem;
  onMove: (item: GearItem, target: string) => void;
  onClose: () => void;
}) {
  const current = matPlacement(item);
  const options = [
    ...CORE_SLOTS.map((slot) => ({ key: slot.key, label: slot.label, icon: slot.icon })),
    { key: MORE_GEAR, label: "More gear", icon: "generic" as const },
  ];
  return (
    <Dialog title={`Move ${item.display_name}`} subtitle="Choose where it sits on your gear page." onClose={onClose} size="sm">
      <ul className={styles.grid}>
        {options.map((option, index) => (
          <li key={option.key}>
            <button
              type="button"
              className={styles.option}
              disabled={option.key === current}
              aria-current={option.key === current || undefined}
              data-autofocus={index === (current === CORE_SLOTS[0].key ? 1 : 0) || undefined}
              onClick={() => onMove(item, option.key)}
            >
              <GearIcon icon={option.icon} className={styles.icon} />
              <span>{option.label}</span>
              {option.key === current && <span className={styles.here}>Here now</span>}
            </button>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}

/** "Add item" in the More gear panel: pick the kind of gear, then the catalogue opens. */
export function AddItemDialog({ onChoose, onClose }: { onChoose: (slot: Slot) => void; onClose: () => void }) {
  return (
    <Dialog title="Add to More gear" subtitle="What kind of gear is it?" onClose={onClose} size="md">
      <div className={styles.zones}>
        {MORE_ZONES.map((zone) => (
          <section key={zone.slug} aria-labelledby={`add-${zone.slug}`}>
            <h3 id={`add-${zone.slug}`} className={styles.zoneTitle}>
              {zone.label}
            </h3>
            <ul className={styles.grid}>
              {zone.slots.map((slot) => (
                <li key={slot.key}>
                  <button type="button" className={styles.option} onClick={() => onChoose(slot)}>
                    <GearIcon icon={slot.icon} className={styles.icon} />
                    <span>{slot.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Dialog>
  );
}
