"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import GearThumb from "@/components/GearThumb";
import ui from "@/components/ui.module.css";
import { nextQuery } from "@/lib/authLogic";
import { listCategories, type GearItem } from "@/lib/gearApi";
import type { GearSetup } from "@/lib/setupsApi";
import { formatWeight } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import FlatLay from "./FlatLay";
import GearList from "./GearList";
import { GearIcon } from "./icons";
import ItemDetails from "./ItemDetails";
import ProductPicker, { PENDING_KEY, type PendingAdd } from "./ProductPicker";
import SetupDialog from "./SetupDialog";
import { CORE_SLOTS, MORE_ZONES, groupItemsBySlot, slotByKey, slotForItem, type Slot } from "./slots";
import { summarize, useMyGear } from "./useMyGear";
import { useSetups } from "./useSetups";
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

function GearContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status: authStatus, user } = useAuth();
  const gear = useMyGear();
  const setupsData = useSetups();
  const [units, setUnits] = useUnits();

  const [view, setView] = useState<"flatlay" | "list">("flatlay");
  const [search, setSearch] = useState("");
  const [picker, setPicker] = useState<PickerState | null>(null);
  const [details, setDetails] = useState<GearItem | null>(null);
  const [setupDialog, setSetupDialog] = useState<{ setup: GearSetup | null } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
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

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => {
      setToast(null);
      setSnapId(null);
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const allItems = gear.items;
  const ownedCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of allItems) {
      if (item.product) counts.set(item.product.id, (counts.get(item.product.id) ?? 0) + 1);
    }
    return counts;
  }, [allItems]);

  // In a setup view only that setup's items show; edits still use the live items.
  const setupIds = activeSetup ? new Set(activeSetup.items.map((item) => item.id)) : null;
  const needle = search.trim().toLowerCase();
  const visibleItems = allItems.filter(
    (item) =>
      (!setupIds || setupIds.has(item.id)) &&
      (!needle ||
        [item.display_name, item.brand_name, item.category.name, item.notes]
          .filter(Boolean)
          .some((value) => value!.toLowerCase().includes(needle))),
  );
  const bySlot = groupItemsBySlot(visibleItems);
  const coreItems = visibleItems.filter((item) => slotForItem(item).core);
  const moreItems = visibleItems.filter((item) => !slotForItem(item).core);
  const coreFilled = CORE_SLOTS.filter((slot) => (groupItemsBySlot(allItems).get(slot.key) ?? []).length > 0).length;
  const { knownGrams, missing } = summarize(visibleItems);

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
    setToast(action === "added" ? `Added ${item.display_name} to your gear.` : `Replaced with ${item.display_name}.`);
  };

  return (
    <main className={styles.page}>
      <div className={styles.texture} aria-hidden="true" />

      <div className={styles.headBar}>
        <h1 className={styles.title}>Your gear</h1>
        {isSignedIn && (
          <div className={ui.chips} role="group" aria-label="Show">
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
          </div>
        )}
      </div>

      {authStatus === "signedOut" && (
        <div className={`${ui.notice} ${styles.banner}`}>
          <p>
            <strong>Sign in to save your setup.</strong> Browse the catalogue now; your gear is saved to your
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

      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
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
          {isSignedIn && (
            <p className={styles.setupSummary}>
              {activeSetup ? (
                <>
                  {activeSetup.item_count} {activeSetup.item_count === 1 ? "item" : "items"} ·{" "}
                  {formatWeight(knownGrams, units)}
                  {missing > 0 && ` known (${missing} without a weight)`} ·{" "}
                  <button type="button" className={ui.ghost} onClick={() => setSetupDialog({ setup: activeSetup })}>
                    Edit setup
                  </button>
                </>
              ) : (
                <>
                  {coreFilled} of {CORE_SLOTS.length} main pieces · {allItems.length}{" "}
                  {allItems.length === 1 ? "item" : "items"} · {formatWeight(knownGrams, units)} known weight
                  {missing > 0 && ` (${missing} without a weight)`}
                </>
              )}
            </p>
          )}
        </div>
        <div className={styles.toolbarRight}>
          <div className={styles.toggle} role="group" aria-label="Units">
            <button type="button" aria-pressed={units === "imperial"} onClick={() => setUnits("imperial")}>
              lb/oz
            </button>
            <button type="button" aria-pressed={units === "metric"} onClick={() => setUnits("metric")}>
              kg/g
            </button>
          </div>
          <div className={styles.toggle} role="group" aria-label="View">
            <button type="button" aria-pressed={view === "flatlay"} onClick={() => setView("flatlay")}>
              Showcase
            </button>
            <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>
              List
            </button>
          </div>
        </div>
      </div>

      {gear.status === "error" && (
        <div className={`${ui.error} ${styles.banner}`} role="alert">
          We couldn&apos;t load your gear: {gear.error}{" "}
          <button type="button" className={ui.ghost} onClick={gear.reload}>
            Try again
          </button>
        </div>
      )}

      <div className={styles.board} aria-busy={gear.status === "loading"}>
        {gear.status === "loading" ? (
          <div className={styles.loadingGrid} aria-label="Loading your gear">
            {Array.from({ length: 7 }, (_, index) => (
              <div key={index} className={`${ui.skeleton} ${styles.loadingTile}`} />
            ))}
          </div>
        ) : view === "flatlay" ? (
          <>
            <section className={styles.showcase} aria-labelledby="main-setup">
              <h2 id="main-setup" className={styles.sectionTitle}>
                Main setup
              </h2>
              <FlatLay
                slots={CORE_SLOTS}
                bySlot={bySlot}
                showEmptySlots={showEmptySlots}
                units={units}
                canEdit={canEdit}
                addDisabled={gear.status === "error"}
                snapId={snapId}
                emptyMessage={
                  showEmptySlots || coreItems.length > 0
                    ? null
                    : activeSetup && !needle
                      ? "No main pieces in this setup yet — edit it to add some."
                      : visibleItems.length === 0
                        ? "No gear matches"
                        : "No main pieces match — see More gear below."
                }
                onAdd={openAdd}
                onOpen={setDetails}
              />
            </section>

            <details className={styles.more} open={moreItems.length > 0 && (Boolean(activeSetup) || Boolean(needle))}>
              <summary className={styles.moreSummary}>
                <span className={styles.sectionTitle}>More gear</span>
                <span className={ui.hint}>
                  {moreItems.length > 0
                    ? `${moreItems.length} ${moreItems.length === 1 ? "item" : "items"}`
                    : "Optional — pillows, filters, headlamps, poles and more"}
                </span>
              </summary>
              <div className={styles.moreZones}>
                {MORE_ZONES.map((zone) => {
                  const zoneSlots = zone.slots.filter(
                    (slot) => showEmptySlots || (bySlot.get(slot.key) ?? []).length > 0,
                  );
                  if (zoneSlots.length === 0) return null;
                  return (
                    <section key={zone.slug} className={styles.zone} aria-labelledby={`zone-${zone.slug}`}>
                      <h3 id={`zone-${zone.slug}`} className={styles.zoneTitle}>
                        {zone.label}
                      </h3>
                      <ul className={styles.tiles}>
                        {zoneSlots.flatMap((slot) => {
                          const items = bySlot.get(slot.key) ?? [];
                          if (items.length === 0) {
                            return [
                              <li key={slot.key}>
                                <button
                                  type="button"
                                  className={`${styles.tile} ${styles.tileEmpty}`}
                                  onClick={() => openAdd(slot)}
                                  aria-label={`Add ${slot.noun}`}
                                >
                                  <GearIcon icon={slot.icon} className={styles.tileIcon} />
                                  <span className={styles.tileName}>{slot.label}</span>
                                  <span className={styles.plusSmall} aria-hidden="true">
                                    +
                                  </span>
                                </button>
                              </li>,
                            ];
                          }
                          return items.map((item) => (
                            <li key={item.id}>
                              <button
                                type="button"
                                className={`${styles.tile} ${styles.tileFilled}`}
                                onClick={() => canEdit && setDetails(item)}
                                aria-label={`${item.display_name}, ${slot.label}. View or edit`}
                              >
                                {item.quantity > 1 && <span className={styles.qty}>×{item.quantity}</span>}
                                <GearThumb icon={slot.icon} productImage={item.product?.image} photoPath={item.image_path} alt="" size="md" />
                                <span className={styles.tileName}>{item.product?.name ?? item.display_name}</span>
                                <span className={styles.tileMeta}>{item.brand_name ?? "Custom"}</span>
                              </button>
                            </li>
                          ));
                        })}
                        {showEmptySlots && (
                          <li>
                            <button
                              type="button"
                              className={`${styles.tile} ${styles.tileAnother}`}
                              onClick={() => openAdd(zone.slots[0])}
                              aria-label={`Add more ${zone.label.toLowerCase()} gear`}
                            >
                              <span className={styles.plusSmall} aria-hidden="true">
                                +
                              </span>
                              <span className={styles.tileMeta}>Add another</span>
                            </button>
                          </li>
                        )}
                      </ul>
                    </section>
                  );
                })}
              </div>
            </details>
          </>
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

      <p className={styles.toast} role="status" aria-live="polite">
        {toast}
      </p>

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
            setToast(`Saved changes to ${item.display_name}.`);
          }}
          onDeleted={(item) => {
            gear.remove(item.id);
            setupsData.reload();
            setDetails(null);
            setToast(`Removed ${item.display_name} from your gear.`);
          }}
          onReplace={(item) => {
            setDetails(null);
            setPicker({ slot: slotForItem(item), replacing: item, resume: null });
          }}
          onClose={() => setDetails(null)}
        />
      )}

      {setupDialog && (
        <SetupDialog
          items={allItems}
          setup={setupDialog.setup}
          onSaved={(setup) => {
            setupsData.reload();
            setSetupDialog(null);
            selectSetup(setup.id);
            setToast(`Saved ${setup.name}.`);
          }}
          onDeleted={() => {
            setupsData.reload();
            setSetupDialog(null);
            selectSetup(null);
            setToast("Setup deleted. Your gear is unchanged.");
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
