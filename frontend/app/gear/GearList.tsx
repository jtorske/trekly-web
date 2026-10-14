"use client";

import GearThumb from "@/components/GearThumb";
import ui from "@/components/ui.module.css";
import type { GearItem } from "@/lib/gearApi";
import { formatWeight, type UnitSystem } from "@/lib/units";
import { slotForItem } from "./slots";
import styles from "./GearList.module.css";

const CONDITION_LABELS: Record<string, string> = {
  new: "New",
  good: "Good",
  worn: "Worn",
  needs_repair: "Needs repair",
  retired: "Retired",
};

/** Accessible list/table view of owned gear, shared by the Gear page and profile. */
export default function GearList({
  items,
  units,
  onOpen,
  compact = false,
}: {
  items: GearItem[];
  units: UnitSystem;
  onOpen?: (item: GearItem) => void;
  compact?: boolean;
}) {
  return (
    <ul className={`${styles.list} ${compact ? styles.compact : ""}`}>
      {items.map((item) => {
        const slot = slotForItem(item);
        const weight = item.weight.effective_g;
        const subtitle = [
          item.kind === "custom" ? [item.custom_brand, item.custom_model].filter(Boolean).join(" ") || null : null,
          item.category.name,
        ]
          .filter(Boolean)
          .join(" · ");
        const content = (
          <>
            <GearThumb
              icon={slot.icon}
              productImage={item.product?.image}
              photoPath={item.image_path}
              alt=""
              size={compact ? "sm" : "md"}
            />
            <span className={styles.body}>
              <span className={styles.name}>{item.display_name}</span>
              <span className={styles.meta}>{subtitle}</span>
              {!compact && (
                <span className={styles.badges}>
                  {item.kind === "custom" && <span className={ui.badge}>Custom</span>}
                  {item.weight.source === "override" && <span className={ui.badge}>Your weight</span>}
                  {item.condition && <span className={ui.badge}>{CONDITION_LABELS[item.condition]}</span>}
                  {item.product?.status === "discontinued" && (
                    <span className={`${ui.badge} ${ui.badgeWarn}`}>Discontinued</span>
                  )}
                </span>
              )}
            </span>
            <span className={styles.numbers}>
              {item.quantity > 1 && <span className={styles.qty}>×{item.quantity}</span>}
              <span className={styles.weight}>
                {weight != null ? formatWeight(weight * item.quantity, units) : "Weight unknown"}
              </span>
            </span>
          </>
        );
        return (
          <li key={item.id}>
            {onOpen ? (
              <button type="button" className={styles.row} onClick={() => onOpen(item)} aria-label={`Edit ${item.display_name}`}>
                {content}
              </button>
            ) : (
              <div className={styles.row}>{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
