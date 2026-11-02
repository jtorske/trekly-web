"use client";

import { useEffect, useId, useRef, useState } from "react";
import GearThumb from "@/components/GearThumb";
import ui from "@/components/ui.module.css";
import type { GearItem } from "@/lib/gearApi";
import { matImage } from "@/lib/gearImage";
import { formatWeight, type UnitSystem } from "@/lib/units";
import { carryOf } from "./baseWeight";
import { GearIcon } from "./icons";
import { MORE_GEAR, ZONES, slotByKey, slotForItem, type Slot } from "./slots";
import type { useGearDrag } from "./useGearDrag";
import styles from "./MoreGearPanel.module.css";

export interface ItemActions {
  onOpen: (item: GearItem) => void;
  onMove: (item: GearItem) => void;
  onRemove: (item: GearItem) => void;
}

const CARRY_TAGS = { worn: "Worn", consumable: "Consumable" } as const;

/** Quick-add chips for common extras, in this order. */
export const QUICK_ADD: { slot: string; label: string }[] = [
  { slot: "headlamp", label: "Headlamp" },
  { slot: "water-filter", label: "Water filter" },
  { slot: "pillow", label: "Pillow" },
  { slot: "trekking-poles", label: "Trekking poles" },
  { slot: "first-aid", label: "First-aid kit" },
  { slot: "bear-safety", label: "Bear spray" },
];

/** The chips stay under a short list too, and go once it has more than this many items. */
export const QUICK_ADD_UNTIL = 3;

function QuickAddChips({ slots, onAdd }: { slots: string[]; onAdd: (slot: Slot) => void }) {
  const chips = QUICK_ADD.filter((chip) => slots.includes(chip.slot));
  if (chips.length === 0) return null;
  return (
    <ul className={styles.chips} aria-label="Quick add">
      {chips.map((chip) => {
        const slot = slotByKey(chip.slot)!;
        return (
          <li key={chip.slot}>
            <button type="button" className={styles.chip} onClick={() => onAdd(slot)} aria-label={`Add a ${chip.label.toLowerCase()}`}>
              <GearIcon icon={slot.icon} className={styles.chipIcon} />
              {chip.label}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** "⋯" disclosure with Edit, Move to… and Remove. Escape or a click outside closes it. */
function ItemMenu({ item, actions }: { item: GearItem; actions: ItemActions }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      toggle.current?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", key);
    wrap.current?.querySelector<HTMLElement>("[data-menu] button")?.focus();
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const run = (action: (item: GearItem) => void) => () => {
    setOpen(false);
    action(item);
  };

  return (
    <div className={styles.menuWrap} ref={wrap}>
      <button
        ref={toggle}
        type="button"
        className={styles.menuButton}
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Actions for ${item.display_name}`}
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
          <circle cx="4.5" cy="10" r="1.6" />
          <circle cx="10" cy="10" r="1.6" />
          <circle cx="15.5" cy="10" r="1.6" />
        </svg>
      </button>
      {open && (
        <div id={menuId} className={styles.menu} data-menu>
          <button type="button" onClick={run(actions.onOpen)}>
            Edit
          </button>
          <button type="button" onClick={run(actions.onMove)}>
            Move to…
          </button>
          <button type="button" className={styles.danger} onClick={run(actions.onRemove)}>
            Remove
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * The right-hand panel's list: everything not on the mat, grouped by
 * category, with small icons and weights. It's also a drop target, so a
 * piece dragged off the mat lands here.
 */
export default function MoreGearPanel({
  items,
  units,
  canEdit,
  drag,
  snapId,
  emptyMessage,
  quickAdd,
  actions,
}: {
  items: GearItem[];
  units: UnitSystem;
  canEdit: boolean;
  drag: ReturnType<typeof useGearDrag>;
  snapId: string | null;
  emptyMessage: string;
  /** All-gear view only: chips for common extras the owner doesn't have yet. */
  quickAdd?: { slots: string[]; onAdd: (slot: Slot) => void } | null;
  actions: ItemActions;
}) {
  const groups = ZONES.map((zone) => ({
    zone,
    items: items.filter((item) => slotForItem(item).zone === zone.slug),
  })).filter((group) => group.items.length > 0);
  const isTarget = drag.drag && !drag.drag.landing;

  return (
    <div
      className={styles.panel}
      data-drop={canEdit ? MORE_GEAR : undefined}
      data-over={isTarget && drag.drag?.over === MORE_GEAR ? true : undefined}
      data-receiving={isTarget ? true : undefined}
    >
      {groups.length === 0 && quickAdd ? (
        <div className={styles.invite}>
          <span className={styles.inviteIcon} aria-hidden="true">
            <GearIcon icon="dryBag" />
          </span>
          <p className={styles.inviteText}>Add the extras you carry</p>
          <QuickAddChips slots={quickAdd.slots} onAdd={quickAdd.onAdd} />
        </div>
      ) : groups.length === 0 ? (
        <p className={styles.empty}>{emptyMessage}</p>
      ) : (
        groups.map(({ zone, items: zoneItems }) => (
          <section key={zone.slug} className={styles.group} aria-labelledby={`more-${zone.slug}`}>
            <h3 id={`more-${zone.slug}`} className={styles.groupTitle}>
              {zone.label}
            </h3>
            <ul className={styles.rows}>
              {zoneItems.map((item) => {
                const slot = slotForItem(item);
                const grams = item.weight.effective_g;
                const carry = carryOf(item);
                const tag = carry === "packed" ? null : CARRY_TAGS[carry];
                return (
                  <li key={item.id} className={styles.row} data-snap={item.id === snapId || undefined}>
                    <button
                      type="button"
                      className={styles.rowMain}
                      onClick={() => canEdit && actions.onOpen(item)}
                      aria-label={`${item.display_name}, ${slot.label}${canEdit ? ". View or edit" : ""}`}
                      {...(canEdit ? drag.sourceProps(item) : {})}
                    >
                      <GearThumb icon={slot.icon} productImage={matImage(item)} alt="" size="sm" />
                      <span className={styles.body}>
                        <span className={styles.name}>
                          {item.product?.name ?? item.display_name}
                          {item.quantity > 1 && <span className={styles.qty}> ×{item.quantity}</span>}
                        </span>
                        <span className={styles.meta}>
                          {item.brand_name ?? "Custom"}
                          {tag && <span className={ui.badge}>{tag}</span>}
                        </span>
                      </span>
                      <span className={styles.weight} data-missing={grams == null || undefined}>
                        {grams != null ? formatWeight(grams * item.quantity, units) : "No weight"}
                      </span>
                    </button>
                    {canEdit && <ItemMenu item={item} actions={actions} />}
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
      {groups.length > 0 && quickAdd && items.length <= QUICK_ADD_UNTIL && (
        <div className={styles.quickAdd}>
          <p className={styles.groupTitle}>Quick add</p>
          <QuickAddChips slots={quickAdd.slots} onAdd={quickAdd.onAdd} />
        </div>
      )}
    </div>
  );
}
