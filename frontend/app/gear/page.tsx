"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import GearThumb from "@/components/GearThumb";
import { matImage } from "@/lib/gearImage";
import ui from "@/components/ui.module.css";
import { nextQuery } from "@/lib/authLogic";
import {
  addMyGear,
  deleteMyGear,
  getProduct,
  listCategories,
  updateMyGear,
  type GearItem,
  type ProductSummary,
} from "@/lib/gearApi";
import { removeImages } from "@/lib/storage";
import { toast } from "@/lib/toast";
import { removeWithUndo } from "@/lib/undo";
import { useHidden } from "@/lib/useHidden";
import type { GearSetup } from "@/lib/setupsApi";
import { formatWeight } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import FlatLay from "./FlatLay";
import GearList from "./GearList";
import ItemDetails from "./ItemDetails";
import MoreGearPanel, { type ItemActions } from "./MoreGearPanel";
import ProductPicker, { PENDING_KEY, type PendingAdd } from "./ProductPicker";
import SetupDialog from "./SetupDialog";
import { AddItemDialog, MoveDialog } from "./SlotChooser";
import {
  CORE_SLOTS,
  MORE_GEAR,
  groupItemsByPlacement,
  matPlacement,
  matSlotFor,
  slotByKey,
  slotForItem,
  type Slot,
} from "./slots";
import { useGearDrag } from "./useGearDrag";
import { useMyGear } from "./useMyGear";
import { useSetups } from "./useSetups";
import WeightSummary from "./WeightSummary";
import styles from "./page.module.css";

type PickerState = { slot: Slot; replacing: GearItem | null; resume: PendingAdd | null };

function takePending(): PendingAdd | null {
  try {
    const raw = window.sessionStorage.getItem(PENDING_KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(PENDING_KEY);
    return JSON.parse(raw) as PendingAdd;
  } catch {
    return null;
  }
}

function placementLabel(placement: string): string {
  return placement === MORE_GEAR ? "More gear" : (slotByKey(placement)?.label ?? "the mat");
}

function GearContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status: authStatus, user } = useAuth();
  const gear = useMyGear();
  const setupsData = useSetups();
  const [units] = useUnits();

  const [view, setView] = useState<"flatlay" | "list">("flatlay");
  const [search, setSearch] = useState("");
  const [picker, setPicker] = useState<PickerState | null>(null);
  const [details, setDetails] = useState<GearItem | null>(null);
  const [moving, setMoving] = useState<GearItem | null>(null);
  const [addingMore, setAddingMore] = useState(false);
  const [setupDialog, setSetupDialog] = useState<{ setup: GearSetup | null } | null>(null);
  const [snapId, setSnapId] = useState<string | null>(null);
  const [categoryNames, setCategoryNames] = useState<Record<string, string>>({});
  const resumed = useRef(false);

  const activeSetupId = searchParams.get("setup");
  const activeSetup = setupsData.setups.find((setup) => setup.id === activeSetupId) ?? null;
  const selectSetup = (id: string | null) =>
    router.replace(id ? `/gear?setup=${encodeURIComponent(id)}` : "/gear", { scroll: false });

  useEffect(() => {
    const controller = new AbortController();
    listCategories(controller.signal)
      .then((tree) => {
        const names: Record<string, string> = {};
        for (const top of tree) {
          names[top.slug] = top.name;
          for (const sub of top.subcategories) names[sub.slug] = sub.name;
        }
        setCategoryNames(names);
      })
      .catch(() => undefined); // Names are cosmetic; slugs still work.
    return () => controller.abort();
  }, []);

  // Back from sign-in with an unsaved selection: reopen it to finish adding.
  useEffect(() => {
    if (resumed.current || searchParams.get("resume") !== "1" || gear.status !== "ready") return;
    resumed.current = true;
    const pending = takePending();
    router.replace("/gear", { scroll: false });
    const slot = pending ? slotByKey(pending.slotKey) : undefined;
    if (pending && slot) queueMicrotask(() => setPicker({ slot, replacing: null, resume: pending }));
  }, [searchParams, gear.status, router]);

  // The new or moved item's snap-into-place plays once.
  useEffect(() => {
    if (!snapId) return;
    const timer = window.setTimeout(() => setSnapId(null), 4000);
    return () => window.clearTimeout(timer);
  }, [snapId]);

  // Items waiting on an Undo toast are already gone from the mat and list.
  const isHidden = useHidden();
  const allItems = useMemo(() => gear.items.filter((item) => !isHidden(`gear:${item.id}`)), [gear.items, isHidden]);
  const ownedCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of allItems) {
      if (item.product) counts.set(item.product.id, (counts.get(item.product.id) ?? 0) + 1);
    }
    return counts;
  }, [allItems]);

  // In a setup view only that setup's items show; edits still use the live items.
  const setupIds = activeSetup ? new Set(activeSetup.items.map((item) => item.id)) : null;
  const scopeItems = setupIds ? allItems.filter((item) => setupIds.has(item.id)) : allItems;
  const needle = search.trim().toLowerCase();
  const visibleItems = scopeItems.filter(
    (item) =>
      !needle ||
      [item.display_name, item.brand_name, item.category.name, item.notes]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(needle)),
  );
  const byPlacement = groupItemsByPlacement(visibleItems);
  const coreItems = visibleItems.filter((item) => matPlacement(item) !== MORE_GEAR);
  const moreItems = byPlacement.get(MORE_GEAR) ?? [];
  const scopePlacement = groupItemsByPlacement(scopeItems);
  const coreFilled = CORE_SLOTS.filter((slot) => (scopePlacement.get(slot.key) ?? []).length > 0).length;

  const isSignedIn = authStatus === "signedIn";
  const canEdit = isSignedIn && gear.status === "ready";
  const showEmptySlots = !activeSetup && !needle;

  const openAdd = (slot: Slot) => setPicker({ slot, replacing: null, resume: null });

  const handleSaved = (item: GearItem, action: "added" | "replaced") => {
    gear.upsert(item);
    setupsData.reload();
    setPicker(null);
    setDetails(null);
    if (action === "added") setSnapId(item.id);
    toast.success(action === "added" ? `Added ${item.display_name} to your gear` : `Replaced with ${item.display_name}`);
  };

  const removeItem = (item: GearItem) =>
    removeWithUndo({
      key: `gear:${item.id}`,
      message: `Removed ${item.display_name} from your gear`,
      what: `remove ${item.display_name}`,
      commit: async () => {
        await deleteMyGear(item.id);
        if (item.image_path) removeImages("gear-photos", [item.image_path]).catch(() => undefined);
      },
      onCommitted: () => {
        gear.remove(item.id);
        setupsData.reload();
      },
    });

  // Moves show straight away and roll back if the save fails, so a drop
  // never waits on the network.
  const moveItem = async (item: GearItem, target: string, announce: boolean) => {
    if (matPlacement(item) === target) return;
    const matSlot = matSlotFor(item, target);
    gear.upsert({ ...item, mat_slot: matSlot });
    setSnapId(item.id);
    try {
      gear.upsert(await updateMyGear(item.id, { mat_slot: matSlot }));
      if (announce) toast.success(`Moved ${item.display_name} to ${placementLabel(target)}`);
    } catch (error) {
      gear.upsert(item);
      toast.failure(`move ${item.display_name}`, error, () => void moveItem(item, target, announce));
    }
  };
  // useGearDrag keeps the latest callback, so this needn't be stable.
  const drag = useGearDrag((item, target) => void moveItem(item, target, false));

  // Quick add from an empty slot's popular picks. Products with sizes, and
  // guests, go through the picker to choose a size or sign in.
  const addProduct = async (slot: Slot, product: ProductSummary) => {
    const resume: PendingAdd = { kind: "catalog", slotKey: slot.key, productId: product.id, variantId: null, quantity: 1 };
    if (!isSignedIn || product.variant_count > 1) {
      setPicker({ slot, replacing: null, resume });
      return;
    }
    try {
      const variantId = product.variant_count === 1 ? (await getProduct(product.id)).variants[0]?.id ?? null : null;
      handleSaved(
        await addMyGear({ client_request_id: crypto.randomUUID(), product_id: product.id, variant_id: variantId }),
        "added",
      );
    } catch (error) {
      toast.failure(`add ${product.display_name}`, error, () => void addProduct(slot, product));
    }
  };

  const actions: ItemActions = {
    onOpen: setDetails,
    onMove: setMoving,
    onRemove: removeItem,
  };

  const ghost = drag.drag;

  return (
    <main className={styles.page}>
      <header className={styles.headBar}>
        <h1 className={styles.title}>Your gear</h1>
        {isSignedIn && (
          <div className={`${ui.chips} ${styles.setups}`} role="group" aria-label="Show">
            <button type="button" className={ui.chip} aria-pressed={!activeSetup} onClick={() => selectSetup(null)}>
              All my gear
            </button>
            {setupsData.setups.map((setup) => (
              <button
                key={setup.id}
                type="button"
                className={ui.chip}
                aria-pressed={activeSetup?.id === setup.id}
                onClick={() => selectSetup(setup.id)}
              >
                {setup.name} <span className={styles.chipCount}>{setup.item_count}</span>
              </button>
            ))}
            <button
              type="button"
              className={ui.ghost}
              onClick={() => setSetupDialog({ setup: null })}
              disabled={gear.status !== "ready"}
            >
              + New setup
            </button>
            {activeSetup && (
              <button type="button" className={ui.ghost} onClick={() => setSetupDialog({ setup: activeSetup })}>
                Edit setup
              </button>
            )}
          </div>
        )}
        <div className={styles.headTools}>
          {isSignedIn && allItems.length > 0 && (
            <label>
              <span className={ui.srOnly}>Search your gear</span>
              <input
                className={`${ui.input} ${styles.searchInput}`}
                type="search"
                placeholder="Search your gear…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
          )}
          <div className={ui.segmented} role="group" aria-label="View">
            <button type="button" aria-pressed={view === "flatlay"} onClick={() => setView("flatlay")}>
              Showcase
            </button>
            <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>
              List
            </button>
          </div>
        </div>
      </header>

      {authStatus === "signedOut" && (
        <div className={`${ui.notice} ${styles.banner}`}>
          <p>
            <strong>Sign in to save your setup.</strong>{" "}Browse the catalogue now; your gear is saved to your
            account so it&apos;s there on every device.
          </p>
          <div className={styles.bannerActions}>
            <Link href={`/signup${nextQuery("/gear")}`} className={ui.primary}>
              Create account
            </Link>
            <Link href={`/login${nextQuery("/gear")}`} className={ui.secondary}>
              Sign in
            </Link>
          </div>
        </div>
      )}

      {gear.status === "error" && (
        <div className={`${ui.error} ${styles.banner}`} role="alert">
          Your gear didn&apos;t load. {gear.error}{" "}
          <button type="button" className={ui.ghost} onClick={gear.reload}>
            Try again
          </button>
        </div>
      )}

      <div className={styles.body}>
        <div className={styles.stage} aria-busy={gear.status === "loading"}>
          {gear.status === "error" ? null : gear.status === "loading" ? (
            <div className={`${ui.skeleton} ${styles.loadingMat}`} aria-label="Loading your gear" />
          ) : view === "flatlay" ? (
            <section className={styles.showcase} aria-labelledby="main-setup">
              <div className={styles.showcaseHead}>
                <h2 id="main-setup" className={styles.sectionTitle}>
                  Main setup
                </h2>
                {canEdit && allItems.length > 0 && (
                  <p className={styles.dragHint}>Drag gear between the mat and More gear</p>
                )}
              </div>
              <div className={styles.matBox}>
                <FlatLay
                  slots={CORE_SLOTS}
                  bySlot={byPlacement}
                  showEmptySlots={showEmptySlots}
                  units={units}
                  canEdit={canEdit}
                  snapId={snapId}
                  ownedCounts={ownedCounts}
                  drag={drag}
                  actions={actions}
                  emptyMessage={
                    showEmptySlots || coreItems.length > 0
                      ? null
                      : activeSetup && !needle
                        ? "No main pieces in this setup yet — edit it to add some."
                        : visibleItems.length === 0
                          ? "No gear matches"
                          : "No main pieces match — see More gear."
                  }
                  onAdd={openAdd}
                  onAddProduct={(slot, product) => void addProduct(slot, product)}
                />
              </div>
            </section>
          ) : (
            <div className={styles.listView}>
              {[
                { key: "main", label: "Main setup", items: coreItems },
                { key: "more", label: "More gear", items: moreItems },
              ].map((group) => (
                <section key={group.key} className={styles.listGroup} aria-labelledby={`list-${group.key}`}>
                  <h2 id={`list-${group.key}`} className={styles.zoneTitle}>
                    {group.label}
                  </h2>
                  {group.items.length > 0 ? (
                    <GearList items={group.items} units={units} onOpen={canEdit ? setDetails : undefined} />
                  ) : (
                    <p className={ui.hint}>Nothing here yet.</p>
                  )}
                </section>
              ))}
              {showEmptySlots && (
                <div className={styles.listAdd}>
                  {CORE_SLOTS.map((slot) => (
                    <button key={slot.key} type="button" className={ui.ghost} onClick={() => openAdd(slot)}>
                      + {slot.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <aside className={styles.side} aria-label="Weight and more gear">
          <WeightSummary
            items={gear.status === "ready" ? scopeItems : []}
            units={units}
            coreFilled={coreFilled}
            coreTotal={CORE_SLOTS.length}
            scopeLabel={activeSetup?.name ?? null}
          />
          <section className={styles.moreCard} aria-labelledby="more-gear">
            <div className={styles.moreHead}>
              <h2 id="more-gear" className={styles.moreTitle}>
                More gear
                {moreItems.length > 0 && <span className={styles.moreCount}>{moreItems.length}</span>}
              </h2>
              {!activeSetup && (
                <button
                  type="button"
                  className={`${ui.secondary} ${styles.addItem}`}
                  onClick={() => setAddingMore(true)}
                  disabled={authStatus === "loading" || (isSignedIn && gear.status !== "ready")}
                >
                  + Add item
                </button>
              )}
            </div>
            <div className={styles.moreScroll}>
              {gear.status === "loading" ? (
                <div className={styles.moreLoading}>
                  {Array.from({ length: 4 }, (_, index) => (
                    <div key={index} className={`${ui.skeleton} ${styles.moreLoadingRow}`} />
                  ))}
                </div>
              ) : (
                <MoreGearPanel
                  items={moreItems}
                  units={units}
                  canEdit={canEdit}
                  drag={drag}
                  snapId={snapId}
                  actions={actions}
                  emptyMessage={
                    needle
                      ? "Nothing else matches."
                      : activeSetup
                        ? "Nothing else in this setup."
                        : "Optional — pillows, filters, headlamps, poles and more."
                  }
                />
              )}
            </div>
          </section>
        </aside>
      </div>

      {ghost && (
        <div
          className={styles.ghost}
          data-landing={ghost.landing ? true : undefined}
          style={{
            transform: ghost.landing
              ? `translate(${ghost.landing.x}px, ${ghost.landing.y}px) translate(-50%, -50%) scale(0.6)`
              : `translate(${ghost.x}px, ${ghost.y}px) translate(-50%, -50%) rotate(-2deg)`,
          }}
          aria-hidden="true"
        >
          <GearThumb icon={slotForItem(ghost.item).icon} productImage={matImage(ghost.item)} alt="" size="sm" />
          <span className={styles.ghostText}>
            <span className={styles.ghostName}>{ghost.item.product?.name ?? ghost.item.display_name}</span>
            <span className={styles.ghostMeta}>
              {ghost.over ? `Drop on ${placementLabel(ghost.over)}` : ghost.item.weight.effective_g != null
                ? formatWeight(ghost.item.weight.effective_g * ghost.item.quantity, units)
                : "Weight unknown"}
            </span>
          </span>
        </div>
      )}

      {picker && (
        <ProductPicker
          slot={picker.slot}
          categoryNames={categoryNames}
          replacing={picker.replacing}
          ownedCounts={ownedCounts}
          isSignedIn={isSignedIn}
          userId={user?.id ?? null}
          units={units}
          resume={picker.resume}
          onSaved={handleSaved}
          onClose={() => setPicker(null)}
        />
      )}

      {addingMore && (
        <AddItemDialog
          onChoose={(slot) => {
            setAddingMore(false);
            openAdd(slot);
          }}
          onClose={() => setAddingMore(false)}
        />
      )}

      {moving && (
        <MoveDialog
          item={moving}
          onMove={(item, target) => {
            setMoving(null);
            void moveItem(item, target, true);
          }}
          onClose={() => setMoving(null)}
        />
      )}

      {details && user && (
        <ItemDetails
          item={details}
          slot={slotForItem(details)}
          categoryNames={categoryNames}
          userId={user.id}
          units={units}
          onSaved={(item) => {
            gear.upsert(item);
            setupsData.reload();
            setDetails(null);
            toast.success(`Saved changes to ${item.display_name}`);
          }}
          onDeleted={(item) => {
            setDetails(null);
            removeItem(item);
          }}
          onReplace={(item) => {
            setDetails(null);
            setPicker({ slot: slotForItem(item), replacing: item, resume: null });
          }}
          onMove={(item) => {
            setDetails(null);
            setMoving(item);
          }}
          onClose={() => setDetails(null)}
        />
      )}

      {setupDialog && (
        <SetupDialog
          items={allItems}
          setup={setupDialog.setup}
          onSaved={(setup) => {
            const before = setupDialog.setup;
            setupsData.reload();
            setSetupDialog(null);
            selectSetup(setup.id);
            toast.success(
              !before
                ? `Created ${setup.name}`
                : before.name !== setup.name
                  ? `Renamed to ${setup.name}`
                  : `Saved ${setup.name}`,
            );
          }}
          onDeleted={() => {
            setupsData.reload();
            setSetupDialog(null);
            selectSetup(null);
            toast.success("Setup deleted. Your gear is unchanged.");
          }}
          onClose={() => setSetupDialog(null)}
        />
      )}
    </main>
  );
}

export default function GearPage() {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <GearContent />
    </Suspense>
  );
}
