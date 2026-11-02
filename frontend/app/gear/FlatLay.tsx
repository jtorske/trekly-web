"use client";

import { useRef, useState, type FocusEvent, type PointerEvent } from "react";
import type { GearItem, ProductImage, ProductSummary } from "@/lib/gearApi";
import { matImage } from "@/lib/gearImage";
import { formatWeight, type UnitSystem } from "@/lib/units";
import { GearIcon } from "./icons";
import type { ItemActions } from "./MoreGearPanel";
import { PlusMark, Silhouette, hasSilhouette } from "./silhouettes";
import SlotSuggestions from "./SlotSuggestions";
import { slotForItem, type Slot } from "./slots";
import type { useGearDrag } from "./useGearDrag";
import styles from "./FlatLay.module.css";

/** Hover before suggestions open, so sweeping the pointer across the mat doesn't flash them. */
const SUGGEST_DELAY_MS = 180;

function itemSubtitle(item: GearItem): string {
  if (item.kind === "custom") return [item.custom_brand, item.custom_model].filter(Boolean).join(" ") || "Custom item";
  return item.variant ? `${item.brand_name} · ${item.variant.name}` : (item.brand_name ?? "");
}

function itemWeight(item: GearItem, units: UnitSystem): string {
  return item.weight.effective_g != null ? formatWeight(item.weight.effective_g * item.quantity, units) : "Weight unknown";
}

/**
 * The catalogue photo, else the item's own silhouette. An item moved to
 * another kind's slot keeps its own shape, or its icon when it has none.
 */
function PieceArt({ item, slotKey, image }: { item: GearItem | null; slotKey: string; image: ProductImage | null }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const home = item ? slotForItem(item) : null;
  if (image && image.url !== failedUrl) {
    // Catalogue images come from many licensed hosts; see GearThumb.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={image.url} alt="" className={styles.photo} loading="lazy" draggable={false} onError={() => setFailedUrl(image.url)} />;
  }
  if (home && home.key !== slotKey) {
    return hasSilhouette(home.key) ? <Silhouette slotKey={home.key} /> : <GearIcon icon={home.icon} className={styles.foreignIcon} />;
  }
  return <Silhouette slotKey={slotKey} />;
}

interface Props {
  slots: Slot[];
  /** Items by mat placement (slots.ts groupItemsByPlacement). */
  bySlot: Map<string, GearItem[]>;
  /** Unfiltered view: empty slots and "add another" are offered. Otherwise missing slots are ghosts. */
  showEmptySlots: boolean;
  units: UnitSystem;
  canEdit: boolean;
  /** Id of an item just added or moved, which plays the snap-into-place animation. */
  snapId: string | null;
  /** Shown over the mat when a filtered view has no main pieces. */
  emptyMessage: string | null;
  onAdd: (slot: Slot) => void;
  /** The owner's gear page only: drag, hover cards and popular picks. */
  ownedCounts?: Map<string, number>;
  drag?: ReturnType<typeof useGearDrag>;
  actions?: ItemActions;
  onAddProduct?: (slot: Slot, product: ProductSummary) => void;
}

/**
 * The Main setup as a flat-lay "knolling" mat: each core slot has a fixed
 * place sized like the real item, shown as its catalogue photo or drawn as a
 * line silhouette. Never the owner's own photo (lib/gearImage.ts). Extra
 * items in a slot sit beside the first, smaller. Every slot is a drop target
 * for useGearDrag; hovering a piece shows its card, hovering an empty slot
 * shows popular picks.
 */
export default function FlatLay({
  slots,
  bySlot,
  showEmptySlots,
  units,
  canEdit,
  snapId,
  emptyMessage,
  ownedCounts,
  drag,
  actions,
  onAdd,
  onAddProduct,
}: Props) {
  const [suggest, setSuggest] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const dragging = Boolean(drag?.drag && !drag.drag.landing);
  const interactive = canEdit && drag && actions;

  const clearTimer = () => {
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = null;
  };
  const suggestHandlers = (slot: Slot) => ({
    onPointerEnter: (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      clearTimer();
      timer.current = window.setTimeout(() => setSuggest(slot.key), SUGGEST_DELAY_MS);
    },
    onPointerLeave: () => {
      clearTimer();
      setSuggest((current) => (current === slot.key ? null : current));
    },
    onFocus: (event: FocusEvent<HTMLElement>) => {
      // Keyboard focus only; a tap goes straight to the picker.
      if (event.target.matches(":focus-visible")) setSuggest(slot.key);
    },
    onBlur: (event: FocusEvent<HTMLElement>) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
        setSuggest((current) => (current === slot.key ? null : current));
      }
    },
  });

  const filledPiece = (item: GearItem, slot: Slot, mini: boolean) => {
    const name = item.product?.name ?? item.display_name;
    const subtitle = itemSubtitle(item);
    return (
      <div key={item.id} className={`${styles.pieceWrap} ${mini ? styles.miniWrap : ""}`}>
        <button
          type="button"
          className={`${styles.piece} ${mini ? styles.mini : ""}`}
          data-state="filled"
          data-snap={item.id === snapId || undefined}
          onClick={() => interactive && actions.onOpen(item)}
          aria-label={interactive ? `Edit ${slot.noun}: ${name}` : `${slot.label}: ${name}`}
          {...(interactive ? drag.sourceProps(item) : {})}
        >
          <span className={styles.art}>
            <PieceArt item={item} slotKey={slot.key} image={matImage(item)} />
            {item.quantity > 1 && <span className={styles.qty}>×{item.quantity}</span>}
          </span>
          <span className={styles.caption}>
            <span className={styles.name}>{name}</span>
            {subtitle && <span className={styles.brand}>{subtitle}</span>}
            <span className={styles.weight}>{itemWeight(item, units)}</span>
          </span>
        </button>
        {interactive && (
          // The card is a drag handle too, so it never blocks dragging the piece.
          <div className={styles.card} data-kind="item" {...drag.sourceProps(item)}>
            <p className={styles.cardName}>{item.product?.name ?? item.display_name}</p>
            <p className={styles.cardMeta}>
              {item.brand_name ?? "Custom"} · <strong>{itemWeight(item, units)}</strong>
            </p>
            <div className={styles.cardActions}>
              <button type="button" onClick={() => actions.onOpen(item)} aria-label={`Edit ${name}`}>
                Edit
              </button>
              <button type="button" onClick={() => actions.onMove(item)} aria-label={`Move ${name} to…`}>
                Move to…
              </button>
              <button
                type="button"
                className={styles.cardDanger}
                onClick={() => actions.onRemove(item)}
                aria-label={`Remove ${name}`}
              >
                Remove
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={styles.wrap} data-dragging={dragging || undefined}>
      <ul className={styles.mat} data-dimmed={emptyMessage ? true : undefined}>
        {slots.map((slot) => {
          const items = bySlot.get(slot.key) ?? [];
          const dropProps = {
            "data-drop": interactive ? slot.key : undefined,
            "data-over": dragging && drag?.drag?.over === slot.key ? true : undefined,
          };

          if (items.length === 0) {
            if (!showEmptySlots) {
              return (
                <li key={slot.key} className={styles.cell} data-slot={slot.key} aria-hidden="true" {...dropProps}>
                  <span className={styles.ghost}>
                    <span className={styles.art}>
                      <Silhouette slotKey={slot.key} />
                    </span>
                  </span>
                </li>
              );
            }
            return (
              <li key={slot.key} className={styles.cell} data-slot={slot.key} {...dropProps}>
                <div className={styles.pieceWrap} {...suggestHandlers(slot)}>
                  <button
                    type="button"
                    className={styles.piece}
                    data-state="empty"
                    onClick={() => onAdd(slot)}
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
                  {suggest === slot.key && !dragging && onAddProduct && (
                    <SlotSuggestions
                      slot={slot}
                      owned={ownedCounts ?? new Map()}
                      units={units}
                      onAdd={(product) => {
                        setSuggest(null);
                        onAddProduct(slot, product);
                      }}
                      onBrowse={() => {
                        setSuggest(null);
                        onAdd(slot);
                      }}
                    />
                  )}
                </div>
              </li>
            );
          }

          const [first, ...extras] = items;
          const offerAnother = showEmptySlots && !slot.single;
          return (
            <li key={slot.key} className={styles.cell} data-slot={slot.key} {...dropProps}>
              <div className={styles.main}>
                {filledPiece(first, slot, false)}
                {offerAnother && (
                  <button
                    type="button"
                    className={styles.another}
                    onClick={() => onAdd(slot)}
                    aria-label={`Add another ${slot.noun}`}
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
