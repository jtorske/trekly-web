"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "@/lib/auth";
import {
  createUserGear,
  deleteUserGear,
  listUserGear,
  updateUserGear,
  type UserGearInput,
  type UserGearItem,
} from "@/lib/userGear";
import {
  CATEGORY_LABELS,
  ESSENTIAL_SLOTS,
  GEAR_CATEGORIES,
  SLOTS_BY_KEY,
  formatWeight,
  type EssentialSlot,
  type GearCategory,
} from "./gearCatalog";
import { GearIcon, iconForCategory } from "./icons";
import { GearPanel, draftFromItem, emptyDraft, type GearDraft } from "./GearPanel";
import styles from "./page.module.css";

const DRAFT_STORAGE_KEY = "trekly:gear-draft";

// Remounts the panel with fresh state each time it opens.
let panelKey = 0;
const nextPanelKey = () => ++panelKey;

type PanelState = { key: number; draft: GearDraft; editing: UserGearItem | null };

function stashDraft(draft: GearDraft) {
  try {
    window.sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
  } catch {
    // Storage can be unavailable (private mode); the draft just won't survive login.
  }
}

function takeStashedDraft(): GearDraft | null {
  try {
    const raw = window.sessionStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
    return JSON.parse(raw) as GearDraft;
  } catch {
    return null;
  }
}

function itemIcon(item: UserGearItem) {
  return item.slot && SLOTS_BY_KEY[item.slot]
    ? SLOTS_BY_KEY[item.slot].icon
    : iconForCategory(item.category);
}

function itemSubtitle(item: UserGearItem): string | null {
  const brandModel = [item.brand, item.model].filter(Boolean).join(" ");
  return brandModel || (item.slot ? null : CATEGORY_LABELS[item.category]);
}

function FilledTile({ item, onOpen }: { item: UserGearItem; onOpen: () => void }) {
  const subtitle = itemSubtitle(item);
  return (
    <li>
      <button
        type="button"
        className={`${styles.tile} ${styles.tileFilled}`}
        onClick={onOpen}
        aria-label={`Edit ${item.name}`}
      >
        {item.quantity > 1 && <span className={styles.qtyBadge}>×{item.quantity}</span>}
        <GearIcon icon={itemIcon(item)} className={styles.tileIcon} />
        <span className={styles.tileName}>{item.name}</span>
        {subtitle && <span className={styles.tileMeta}>{subtitle}</span>}
        <span className={styles.tileWeight}>
          {item.weight_g != null ? formatWeight(item.weight_g * item.quantity) : "Add weight"}
        </span>
      </button>
    </li>
  );
}

function EmptySlotTile({ slot, onAdd }: { slot: EssentialSlot; onAdd: () => void }) {
  return (
    <li>
      <button
        type="button"
        className={`${styles.tile} ${styles.tileEmpty}`}
        onClick={onAdd}
        aria-label={`Add ${slot.label.toLowerCase()}`}
      >
        <GearIcon icon={slot.icon} className={styles.tileIcon} />
        <span className={styles.tileName}>{slot.label}</span>
        <span className={styles.plus} aria-hidden="true">
          +
        </span>
      </button>
    </li>
  );
}

function AddOtherTile({ category, onAdd }: { category: GearCategory; onAdd: () => void }) {
  return (
    <li>
      <button
        type="button"
        className={`${styles.tile} ${styles.tileAddOther}`}
        onClick={onAdd}
        aria-label={`Add other ${CATEGORY_LABELS[category].toLowerCase()} gear`}
      >
        <span className={styles.plus} aria-hidden="true">
          +
        </span>
        <span className={styles.tileMeta}>Add item</span>
      </button>
    </li>
  );
}

export default function GearPage() {
  const { session, isLoading: isSessionLoading } = useSession();
  const userId = session?.user.id ?? null;

  const [gear, setGear] = useState<{
    userId: string;
    items: UserGearItem[];
    error: string | null;
  } | null>(null);
  const [view, setView] = useState<"flatlay" | "list">("flatlay");
  const [filter, setFilter] = useState<GearCategory | "all">("all");
  const [panel, setPanel] = useState<PanelState | null>(null);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    listUserGear()
      .then((items) => {
        if (cancelled) return;
        setGear({ userId, items, error: null });
        // Coming back from login/signup with an unsaved item: reopen it.
        const draft = takeStashedDraft();
        if (draft) setPanel({ key: nextPanelKey(), draft, editing: null });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setGear({
          userId,
          items: [],
          error: error instanceof Error ? error.message : "Unknown error",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const isLoadingGear = userId !== null && gear?.userId !== userId;
  const items = useMemo(
    () => (userId && gear?.userId === userId ? gear.items : []),
    [gear, userId],
  );
  const loadError = userId && gear?.userId === userId ? gear.error : null;

  const filledSlots = useMemo(
    () => new Set(items.map((item) => item.slot).filter(Boolean) as string[]),
    [items],
  );
  const essentialsFilled = ESSENTIAL_SLOTS.filter((slot) => filledSlots.has(slot.key)).length;

  const { totalG, missingWeight } = useMemo(() => {
    let total = 0;
    let missing = 0;
    for (const item of items) {
      if (item.weight_g == null) missing += 1;
      else total += item.weight_g * item.quantity;
    }
    return { totalG: total, missingWeight: missing };
  }, [items]);

  const visibleCategories = GEAR_CATEGORIES.filter(
    (category) => filter === "all" || category.key === filter,
  );

  const openAdd = (category: GearCategory, slot?: string) =>
    setPanel({ key: nextPanelKey(), draft: emptyDraft(category, slot), editing: null });

  const openEdit = (item: UserGearItem) =>
    setPanel({ key: nextPanelKey(), draft: draftFromItem(item), editing: item });

  const replaceItems = (update: (current: UserGearItem[]) => UserGearItem[]) =>
    setGear((current) =>
      current ? { ...current, items: update(current.items) } : current,
    );

  const handleSave = async (input: UserGearInput) => {
    if (panel?.editing) {
      const saved = await updateUserGear(panel.editing.id, input);
      replaceItems((current) => current.map((item) => (item.id === saved.id ? saved : item)));
    } else {
      const saved = await createUserGear(input);
      replaceItems((current) => [...current, saved]);
    }
    setPanel(null);
  };

  const handleDelete = async () => {
    if (!panel?.editing) return;
    const id = panel.editing.id;
    await deleteUserGear(id);
    replaceItems((current) => current.filter((item) => item.id !== id));
    setPanel(null);
  };

  return (
    <main className={styles.page}>
      <div className={styles.texture} aria-hidden="true" />

      <div className={styles.intro}>
        <h1 className={styles.title}>Your gear</h1>
        <p className={styles.subtitle}>
          Lay out your kit once. Fill in each piece as you go, and Trekly keeps
          track of what you carry and what it weighs.
        </p>
      </div>

      {!isSessionLoading && !session && (
        <div className={styles.guestBanner}>
          <p>
            <strong>Log in to save your gear.</strong> You can look around and
            fill in items, but your collection is only saved to an account.
          </p>
          <div className={styles.guestActions}>
            <Link href="/signup?next=/gear" className={styles.primaryButton}>
              Sign up
            </Link>
            <Link href="/login?next=/gear" className={styles.secondaryButton}>
              Log in
            </Link>
          </div>
        </div>
      )}

      <section className={styles.summary} aria-label="Gear summary">
        <div className={styles.progress}>
          <p className={styles.progressLabel}>
            <strong>
              {essentialsFilled} of {ESSENTIAL_SLOTS.length}
            </strong>{" "}
            essentials filled
          </p>
          <div
            className={styles.progressTrack}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={ESSENTIAL_SLOTS.length}
            aria-valuenow={essentialsFilled}
            aria-label="Essential gear filled"
          >
            <div
              className={styles.progressFill}
              style={{ width: `${(essentialsFilled / ESSENTIAL_SLOTS.length) * 100}%` }}
            />
          </div>
        </div>
        <div className={styles.weight}>
          <span className={styles.weightValue}>{formatWeight(totalG)}</span>
          <span className={styles.weightLabel}>
            total gear weight
            {missingWeight > 0 &&
              ` · ${missingWeight} ${missingWeight === 1 ? "item" : "items"} without a weight`}
          </span>
        </div>
      </section>

      <div className={styles.toolbar}>
        <div className={styles.filters} role="group" aria-label="Filter by category">
          <button
            type="button"
            className={styles.chip}
            aria-pressed={filter === "all"}
            onClick={() => setFilter("all")}
          >
            All
          </button>
          {GEAR_CATEGORIES.map((category) => (
            <button
              key={category.key}
              type="button"
              className={styles.chip}
              aria-pressed={filter === category.key}
              onClick={() => setFilter(category.key)}
            >
              {category.label}
            </button>
          ))}
        </div>

        <div className={styles.viewToggle} role="group" aria-label="View">
          <button
            type="button"
            aria-pressed={view === "flatlay"}
            onClick={() => setView("flatlay")}
          >
            Flat lay
          </button>
          <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>
            List
          </button>
        </div>
      </div>

      {loadError && (
        <p className={styles.error} role="alert">
          We couldn&apos;t load your gear: {loadError}
        </p>
      )}

      <div className={`${styles.board} ${isLoadingGear ? styles.loading : ""}`} aria-busy={isLoadingGear}>
        {view === "flatlay" ? (
          <div className={styles.flatlay}>
            {visibleCategories.map((category) => {
              const categoryItems = items.filter((item) => item.category === category.key);
              const slots = ESSENTIAL_SLOTS.filter((slot) => slot.category === category.key);
              const extras = categoryItems.filter(
                (item) => !item.slot || !slots.some((slot) => slot.key === item.slot),
              );
              return (
                <section key={category.key} className={styles.group}>
                  <h2 className={styles.groupTitle}>{category.label}</h2>
                  <ul className={styles.tiles}>
                    {slots.map((slot) => {
                      const slotItems = categoryItems.filter((item) => item.slot === slot.key);
                      return slotItems.length > 0 ? (
                        slotItems.map((item) => (
                          <FilledTile key={item.id} item={item} onOpen={() => openEdit(item)} />
                        ))
                      ) : (
                        <EmptySlotTile
                          key={slot.key}
                          slot={slot}
                          onAdd={() => openAdd(category.key, slot.key)}
                        />
                      );
                    })}
                    {extras.map((item) => (
                      <FilledTile key={item.id} item={item} onOpen={() => openEdit(item)} />
                    ))}
                    <AddOtherTile category={category.key} onAdd={() => openAdd(category.key)} />
                  </ul>
                </section>
              );
            })}
          </div>
        ) : (
          <div className={styles.listView}>
            {visibleCategories.map((category) => {
              const categoryItems = items.filter((item) => item.category === category.key);
              return (
                <section key={category.key} className={styles.listGroup}>
                  <div className={styles.listHeader}>
                    <h2 className={styles.groupTitle}>{category.label}</h2>
                    <button
                      type="button"
                      className={styles.textButton}
                      onClick={() => openAdd(category.key)}
                    >
                      + Add {category.label.toLowerCase()}
                    </button>
                  </div>
                  {categoryItems.length === 0 ? (
                    <p className={styles.listEmpty}>Nothing here yet.</p>
                  ) : (
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th scope="col">Item</th>
                          <th scope="col">Brand / model</th>
                          <th scope="col" className={styles.numeric}>
                            Qty
                          </th>
                          <th scope="col" className={styles.numeric}>
                            Weight
                          </th>
                          <th scope="col">
                            <span className={styles.srOnly}>Actions</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {categoryItems.map((item) => (
                          <tr key={item.id}>
                            <td>
                              {item.name}
                              {item.slot && SLOTS_BY_KEY[item.slot] && (
                                <span className={styles.essentialTag}>Essential</span>
                              )}
                            </td>
                            <td>{[item.brand, item.model].filter(Boolean).join(" ") || "—"}</td>
                            <td className={styles.numeric}>{item.quantity}</td>
                            <td className={styles.numeric}>
                              {item.weight_g != null
                                ? formatWeight(item.weight_g * item.quantity)
                                : "—"}
                            </td>
                            <td className={styles.numeric}>
                              <button
                                type="button"
                                className={styles.textButton}
                                onClick={() => openEdit(item)}
                                aria-label={`Edit ${item.name}`}
                              >
                                Edit
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>

      {panel && (
        <GearPanel
          key={panel.key}
          initialDraft={panel.draft}
          isEditing={panel.editing !== null}
          isSignedIn={session !== null}
          onSave={handleSave}
          onDelete={panel.editing ? handleDelete : undefined}
          onRequireAuth={stashDraft}
          onClose={() => setPanel(null)}
        />
      )}
    </main>
  );
}
