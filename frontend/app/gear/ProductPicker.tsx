"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import Dialog from "@/components/Dialog";
import GearThumb from "@/components/GearThumb";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { nextQuery } from "@/lib/authLogic";
import {
  addMyGear,
  getProduct,
  listBrands,
  searchProducts,
  updateMyGear,
  type Brand,
  type GearItem,
  type ProductDetail,
  type ProductSummary,
  type WeightUnit,
} from "@/lib/gearApi";
import { uploadImage, validateImage } from "@/lib/storage";
import {
  bottleCapacityFilters,
  formatCapacity,
  formatSpecValue,
  formatWeight,
  gramsFromInput,
  gramsToInput,
  WEIGHT_BASIS_LABELS,
  WEIGHT_INPUT_UNITS,
  weightFilters,
  weightInputUnit,
  type UnitSystem,
} from "@/lib/units";
import { GearIcon } from "./icons";
import type { Slot } from "./slots";
import styles from "./ProductPicker.module.css";

function capacityFilters(slotKey: string, units: UnitSystem): { label: string; min?: number; max?: number }[] | undefined {
  if (slotKey === "water-bottle") return bottleCapacityFilters(units);
  return CAPACITY_SLOTS[slotKey];
}

// Pack volumes read in litres in both systems.
const CAPACITY_SLOTS: Record<string, { label: string; min?: number; max?: number }[]> = {
  backpack: [
    { label: "Any size" },
    { label: "Under 45 L", max: 45000 },
    { label: "45–60 L", min: 45000, max: 60000 },
    { label: "60 L+", min: 60000 },
  ],
};

export const PENDING_KEY = "trekly:gear-pending";

export type PendingAdd =
  | { kind: "catalog"; slotKey: string; productId: string; variantId: string | null; quantity: number }
  | { kind: "custom"; slotKey: string; draft: CustomDraft };

interface CustomDraft {
  name: string;
  category: string;
  brand: string;
  model: string;
  weight: string;
  weightUnit: WeightUnit;
  notes: string;
}

function weightLabel(product: ProductSummary, units: UnitSystem): string | null {
  if (product.weight_g != null) return formatWeight(product.weight_g, units);
  if (product.weight_range_g) {
    const [low, high] = product.weight_range_g;
    return low === high ? formatWeight(low, units) : `${formatWeight(low, units)}–${formatWeight(high, units)}`;
  }
  return null;
}

function stashPending(pending: PendingAdd) {
  try {
    window.sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
  } catch {
    // Storage unavailable: the selection just won't survive sign-in.
  }
}

export default function ProductPicker({
  slot,
  categoryNames,
  replacing,
  ownedCounts,
  isSignedIn,
  userId,
  units,
  resume,
  onSaved,
  onClose,
}: {
  slot: Slot;
  categoryNames: Record<string, string>;
  /** When set, choosing a product replaces this item instead of adding one. */
  replacing?: GearItem | null;
  ownedCounts: Map<string, number>;
  isSignedIn: boolean;
  userId: string | null;
  units: UnitSystem;
  resume?: PendingAdd | null;
  onSaved: (item: GearItem, action: "added" | "replaced") => void;
  onClose: () => void;
}) {
  const [step, setStep] = useState<"browse" | "confirm" | "custom">(
    resume?.kind === "custom" ? "custom" : "browse",
  );
  const [query, setQuery] = useState("");
  const [subtype, setSubtype] = useState<string>("");
  const [brand, setBrand] = useState("");
  const [maxWeight, setMaxWeight] = useState<number | null>(null);
  const [capacityIndex, setCapacityIndex] = useState(0);
  const [brands, setBrands] = useState<Brand[]>([]);

  const [results, setResults] = useState<{
    key: string;
    items: ProductSummary[];
    total: number;
    next: string | null;
    error: string | null;
  } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const [selected, setSelected] = useState<{ id: string; detail: ProductDetail | null; error: string | null } | null>(
    resume?.kind === "catalog" ? { id: resume.productId, detail: null, error: null } : null,
  );
  const [variantId, setVariantId] = useState<string | null>(resume?.kind === "catalog" ? resume.variantId : null);
  const [quantity, setQuantity] = useState(resume?.kind === "catalog" ? resume.quantity : 1);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);
  // One id per dialog: a retried or double-submitted add returns the same item.
  const [requestId] = useState(() => crypto.randomUUID());

  const categoryFilter = subtype || slot.categories.join(",");
  const capacityOptions = capacityFilters(slot.key, units);
  const capacity = capacityOptions?.[capacityIndex];
  const searchKey = JSON.stringify([query.trim(), categoryFilter, brand, maxWeight, capacity?.min, capacity?.max]);

  useEffect(() => {
    const controller = new AbortController();
    listBrands(slot.categories.join(","), controller.signal)
      .then(setBrands)
      .catch(() => setBrands([]));
    return () => controller.abort();
  }, [slot]);

  useEffect(() => {
    if (step !== "browse") return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchProducts(
        { q: query.trim(), category: categoryFilter, brand: brand || undefined, limit: 12 },
        controller.signal,
        { max_weight_g: maxWeight, min_capacity_ml: capacity?.min, max_capacity_ml: capacity?.max },
      )
        .then((page) =>
          setResults({ key: searchKey, items: page.items, total: page.total, next: page.next_cursor, error: null }),
        )
        .catch((error: unknown) => {
          if ((error as { name?: string }).name === "AbortError") return;
          setResults({
            key: searchKey,
            items: [],
            total: 0,
            next: null,
            error: error instanceof Error ? error.message : "Couldn't load products.",
          });
        });
    }, 220);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [step, query, categoryFilter, brand, maxWeight, capacity?.min, capacity?.max, searchKey]);

  useEffect(() => {
    if (!selected || selected.detail || selected.error) return;
    const controller = new AbortController();
    getProduct(selected.id, controller.signal)
      .then((detail) => {
        setSelected({ id: detail.id, detail, error: null });
        setVariantId((current) => current ?? (detail.variants.length === 1 ? detail.variants[0].id : null));
        setStep("confirm");
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setSelected((current) =>
          current ? { ...current, error: error instanceof Error ? error.message : "Couldn't load that product." } : current,
        );
      });
    return () => controller.abort();
  }, [selected]);

  const loadMore = async () => {
    if (!results?.next) return;
    setLoadingMore(true);
    try {
      const page = await searchProducts(
        { q: query.trim(), category: categoryFilter, brand: brand || undefined, cursor: results.next, limit: 12 },
        undefined,
        { max_weight_g: maxWeight, min_capacity_ml: capacity?.min, max_capacity_ml: capacity?.max },
      );
      setResults((current) =>
        current ? { ...current, items: [...current.items, ...page.items], next: page.next_cursor } : current,
      );
    } catch {
      // Keep what's shown; the button stays available to retry.
    } finally {
      setLoadingMore(false);
    }
  };

  const isLoading = step === "browse" && results?.key !== searchKey;
  const filtersActive = Boolean(query.trim() || subtype || brand || maxWeight || capacityIndex);
  const detail = selected?.detail ?? null;
  const ownedCount = detail ? ownedCounts.get(detail.id) ?? 0 : 0;
  const needsVariant = Boolean(detail && detail.variants.length > 1 && !variantId);

  const confirm = async () => {
    if (!detail) return;
    if (!isSignedIn) {
      stashPending({ kind: "catalog", slotKey: slot.key, productId: detail.id, variantId, quantity });
      setNeedsAuth(true);
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      if (replacing) {
        const saved = await updateMyGear(replacing.id, {
          product_id: detail.id,
          variant_id: variantId,
          // The old override described the old product's weight.
          weight_override: null,
        });
        onSaved(saved, "replaced");
      } else {
        const saved = await addMyGear({
          client_request_id: requestId,
          product_id: detail.id,
          variant_id: variantId,
          quantity,
        });
        onSaved(saved, "added");
      }
    } catch (error) {
      // Nothing on the mat changes unless the save succeeded.
      setSaveError(error instanceof ApiError ? error.message : "That didn't save. Try again.");
      setSaving(false);
    }
  };

  const title = replacing
    ? `Replace ${replacing.display_name}`
    : step === "custom"
      ? `Add a custom ${slot.noun}`
      : `Choose your ${slot.noun}`;

  const authPrompt = needsAuth && (
    <div className={ui.notice} role="status">
      <p>
        <strong>Sign in to save your gear.</strong>{" "}We&apos;ll keep your selection and bring you
        back to finish adding it.
      </p>
      <div className={styles.authActions}>
        <Link href={`/signup${nextQuery("/gear?resume=1")}`} className={ui.primary}>
          Create account
        </Link>
        <Link href={`/login${nextQuery("/gear?resume=1")}`} className={ui.secondary}>
          Sign in
        </Link>
      </div>
    </div>
  );

  if (step === "custom") {
    return (
      <Dialog
        title={title}
        subtitle="For gear that isn't in the catalogue. Only the name is required."
        onClose={onClose}
        busy={saving}
        size="md"
      >
        <CustomItemForm
          slot={slot}
          categoryNames={categoryNames}
          isSignedIn={isSignedIn}
          userId={userId}
          units={units}
          initial={resume?.kind === "custom" ? resume.draft : null}
          requestId={requestId}
          replacing={replacing ?? null}
          onBack={() => setStep("browse")}
          onSaved={(item) => onSaved(item, replacing ? "replaced" : "added")}
          onNeedsAuth={(draft) => {
            stashPending({ kind: "custom", slotKey: slot.key, draft });
          }}
          onBusyChange={setSaving}
        />
      </Dialog>
    );
  }

  if (step === "confirm" && detail) {
    const variant = detail.variants.find((v) => v.id === variantId) ?? null;
    const shownWeight = variant?.weight_g ?? detail.weight_g;
    const shownBasis = variant?.weight_basis ?? detail.weight_basis;
    return (
      <Dialog
        title={replacing ? `Replace with ${detail.name}?` : `Add ${detail.name}?`}
        subtitle={detail.brand.name}
        onClose={onClose}
        busy={saving}
        footer={
          <>
            <button type="button" className={ui.ghost} onClick={() => setStep("browse")} disabled={saving}>
              ← Back to results
            </button>
            <button
              type="button"
              className={ui.primary}
              onClick={confirm}
              disabled={saving || needsVariant}
            >
              {saving
                ? "Saving…"
                : replacing
                  ? "Replace in my gear"
                  : ownedCount > 0
                    ? "Add another to my gear"
                    : "Add to my gear"}
            </button>
          </>
        }
      >
        <div className={styles.confirm}>
          <GearThumb icon={slot.icon} productImage={detail.image} alt={detail.display_name} size="lg" />
          <div className={styles.confirmInfo}>
            <p className={styles.confirmMeta}>
              {detail.category.name}
              {detail.status === "discontinued" && <span className={`${ui.badge} ${ui.badgeWarn}`}>Discontinued</span>}
            </p>
            {shownWeight != null ? (
              <p className={styles.confirmWeight}>
                {formatWeight(shownWeight, units)}
                {shownBasis && <span> · {WEIGHT_BASIS_LABELS[shownBasis] ?? shownBasis}</span>}
              </p>
            ) : (
              <p className={styles.confirmWeightUnknown}>
                {detail.variants.length > 1 && !variant ? "Choose a size to see its weight." : "Weight not published."}
              </p>
            )}
            {detail.capacity_ml != null && <p className={styles.confirmMeta}>{formatCapacity(detail.capacity_ml, units)}</p>}
          </div>
        </div>

        {replacing && (
          <p className={ui.notice}>
            This replaces <strong>{replacing.display_name}</strong> in your gear. Your quantity, notes and
            condition stay; any weight you entered for the old item is cleared.
          </p>
        )}

        {detail.variants.length > 1 && (
          <fieldset className={styles.variants}>
            <legend className={ui.label}>Size or version</legend>
            {detail.variants.map((option) => (
              <label key={option.id} className={styles.variant}>
                <input
                  type="radio"
                  name="variant"
                  value={option.id}
                  checked={variantId === option.id}
                  onChange={() => setVariantId(option.id)}
                />
                <span>{option.name}</span>
                <span className={styles.variantMeta}>
                  {[
                    option.weight_g != null ? formatWeight(option.weight_g, units) : null,
                    option.capacity_ml != null ? formatCapacity(option.capacity_ml, units) : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </label>
            ))}
          </fieldset>
        )}

        {detail.specs.length > 0 && (
          <dl className={styles.specs}>
            {detail.specs.map((spec) => (
              <div key={spec.key} className={styles.spec}>
                <dt>{spec.label}</dt>
                <dd>{formatSpecValue(spec.value, spec.unit, units)}</dd>
              </div>
            ))}
          </dl>
        )}

        {!replacing && (
          <div className={styles.quantity}>
            <label className={ui.label} htmlFor="picker-quantity">
              How many do you own?
            </label>
            <input
              id="picker-quantity"
              className={`${ui.input} ${styles.quantityInput}`}
              type="number"
              min={1}
              max={99}
              value={quantity}
              onChange={(event) => setQuantity(Math.min(99, Math.max(1, Number(event.target.value) || 1)))}
            />
          </div>
        )}

        {ownedCount > 0 && !replacing && (
          <p className={ui.notice}>
            You already have {ownedCount === 1 ? "this" : `${ownedCount} of these`} in your gear. Adding it
            again creates a separate item — to change how many you own, edit the existing one instead.
          </p>
        )}

        {detail.sources[0]?.url && (
          <p className={ui.hint}>
            Specs from the{" "}
            <a href={detail.sources[0].url} target="_blank" rel="noopener noreferrer" className={styles.link}>
              manufacturer&apos;s page
            </a>
            {detail.verified_at && <>, checked {new Date(detail.verified_at).toLocaleDateString()}</>}.
          </p>
        )}
        {saveError && (
          <p className={ui.error} role="alert">
            {saveError}
          </p>
        )}
        {authPrompt}
      </Dialog>
    );
  }

  return (
    <Dialog
      title={title}
      subtitle={
        replacing
          ? `Pick the ${slot.noun} you're switching to.`
          : `Pick the exact model you own. Only ${slot.label.toLowerCase()} products are shown.`
      }
      onClose={onClose}
      size="lg"
      footer={
        <button type="button" className={ui.ghost} onClick={() => setStep("custom")}>
          Can&apos;t find yours? Add a custom {slot.noun}
        </button>
      }
    >
      <div className={styles.filters}>
        <label className={styles.search}>
          <span className={ui.srOnly}>Search {slot.label.toLowerCase()} products</span>
          <input
            className={ui.input}
            type="search"
            placeholder={`Search ${slot.label.toLowerCase()} by name or brand…`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
          />
        </label>
        <div className={styles.filterRow}>
          {slot.categories.length > 1 && (
            <div className={ui.chips} role="group" aria-label="Type">
              <button type="button" className={ui.chip} aria-pressed={!subtype} onClick={() => setSubtype("")}>
                All types
              </button>
              {slot.categories.map((slug) => (
                <button
                  key={slug}
                  type="button"
                  className={ui.chip}
                  aria-pressed={subtype === slug}
                  onClick={() => setSubtype(slug)}
                >
                  {categoryNames[slug] ?? slug}
                </button>
              ))}
            </div>
          )}
          <label className={styles.select}>
            <span className={ui.srOnly}>Brand</span>
            <select className={ui.input} value={brand} onChange={(event) => setBrand(event.target.value)}>
              <option value="">All brands</option>
              {brands.map((option) => (
                <option key={option.slug} value={option.slug}>
                  {option.name} ({option.product_count})
                </option>
              ))}
            </select>
          </label>
          <label className={styles.select}>
            <span className={ui.srOnly}>Weight</span>
            <select
              className={ui.input}
              value={maxWeight ?? ""}
              onChange={(event) => setMaxWeight(event.target.value ? Number(event.target.value) : null)}
            >
              {weightFilters(units).map((option) => (
                <option key={option.label} value={option.grams ?? ""}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {capacityOptions && (
            <label className={styles.select}>
              <span className={ui.srOnly}>Capacity</span>
              <select
                className={ui.input}
                value={capacityIndex}
                onChange={(event) => setCapacityIndex(Number(event.target.value))}
              >
                {capacityOptions.map((option, index) => (
                  <option key={option.label} value={index}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </div>

      <div className={styles.results} aria-live="polite" aria-busy={isLoading}>
        {selected?.error && (
          <p className={ui.error} role="alert">
            {selected.error}{" "}
            <button type="button" className={ui.ghost} onClick={() => setSelected({ ...selected, error: null })}>
              Try again
            </button>
          </p>
        )}
        {results?.error && !isLoading ? (
          <div className={styles.state}>
            <p className={ui.error} role="alert">
              {results.error}
            </p>
            <button type="button" className={ui.secondary} onClick={() => setResults(null)}>
              Try again
            </button>
          </div>
        ) : !results || (isLoading && results.items.length === 0) ? (
          <ul className={styles.grid} aria-label="Loading products">
            {Array.from({ length: 6 }, (_, index) => (
              <li key={index} className={`${ui.skeleton} ${styles.skeletonCard}`} />
            ))}
          </ul>
        ) : results.items.length === 0 ? (
          <div className={styles.state}>
            <GearIcon icon={slot.icon} className={styles.stateIcon} />
            {filtersActive ? (
              <p>No {slot.label.toLowerCase()} products match those filters.</p>
            ) : (
              <p>
                We don&apos;t have verified {slot.label.toLowerCase()} products in the catalogue yet. Add yours as a
                custom item — it works just the same on your mat.
              </p>
            )}
            <button type="button" className={ui.primary} onClick={() => setStep("custom")}>
              Add a custom {slot.noun}
            </button>
          </div>
        ) : (
          <>
            <p className={ui.hint}>
              {results.total} {results.total === 1 ? "product" : "products"}
            </p>
            <ul className={`${styles.grid} ${isLoading ? styles.stale : ""}`}>
              {results.items.map((product) => {
                const owned = ownedCounts.get(product.id) ?? 0;
                const weight = weightLabel(product, units);
                const isSelecting = selected?.id === product.id && !selected.detail && !selected.error;
                return (
                  <li key={product.id}>
                    <button
                      type="button"
                      className={styles.card}
                      onClick={() => setSelected({ id: product.id, detail: null, error: null })}
                      aria-label={`Select ${product.display_name}`}
                      disabled={isSelecting}
                    >
                      <GearThumb icon={slot.icon} productImage={product.image} alt="" size="md" />
                      <span className={styles.cardBody}>
                        <span className={styles.cardBrand}>{product.brand.name}</span>
                        <span className={styles.cardName}>{product.name}</span>
                        <span className={styles.cardMeta}>
                          {[weight, product.capacity_ml != null ? formatCapacity(product.capacity_ml, units) : null, ...product.key_specs.slice(0, 1).map((s) => `${s.label} ${formatSpecValue(s.value, s.unit, units)}`)]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                        <span className={styles.cardBadges}>
                          {product.variant_count > 1 && <span className={ui.badge}>{product.variant_count} sizes</span>}
                          {product.status === "discontinued" && (
                            <span className={`${ui.badge} ${ui.badgeWarn}`}>Discontinued</span>
                          )}
                          {owned > 0 && <span className={ui.badge}>In your gear</span>}
                        </span>
                      </span>
                      {isSelecting && <span className={styles.cardLoading}>Loading…</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
            {results.next && (
              <div className={styles.more}>
                <button type="button" className={ui.secondary} onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? "Loading…" : "Show more"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}

function CustomItemForm({
  slot,
  categoryNames,
  isSignedIn,
  userId,
  units,
  initial,
  requestId,
  replacing,
  onBack,
  onSaved,
  onNeedsAuth,
  onBusyChange,
}: {
  slot: Slot;
  categoryNames: Record<string, string>;
  isSignedIn: boolean;
  userId: string | null;
  units: UnitSystem;
  initial: CustomDraft | null;
  requestId: string;
  replacing: GearItem | null;
  onBack: () => void;
  onSaved: (item: GearItem) => void;
  onNeedsAuth: (draft: CustomDraft) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [draft, setDraft] = useState<CustomDraft>(() => {
    if (!initial) {
      return { name: "", category: slot.categories[0], brand: "", model: "", weight: "", weightUnit: weightInputUnit(units), notes: "" };
    }
    // A draft stashed before a units change: show its weight in the current units.
    const weightUnit = weightInputUnit(units, initial.weightUnit);
    const grams = gramsFromInput(initial.weight, initial.weightUnit);
    return { ...initial, weightUnit, weight: grams == null ? initial.weight : gramsToInput(grams, weightUnit) };
  });
  const [photo, setPhoto] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);

  const update = (patch: Partial<CustomDraft>) => setDraft((current) => ({ ...current, ...patch }));
  const categoryOptions = useMemo(() => slot.categories, [slot]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (!draft.name.trim()) nextErrors.name = "Give your item a name.";
    if (draft.weight.trim() && gramsFromInput(draft.weight, draft.weightUnit) == null) nextErrors.weight = "Enter a positive number.";
    if (photo) {
      const problem = await validateImage(photo, "gear-photos");
      if (problem) nextErrors.photo = problem;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    if (!isSignedIn || !userId) {
      onNeedsAuth(draft);
      setNeedsAuth(true);
      return;
    }

    setSaving(true);
    onBusyChange(true);
    setError(null);
    try {
      const imagePath = photo ? await uploadImage("gear-photos", userId, photo) : undefined;
      const payload = {
        custom_name: draft.name.trim(),
        category: draft.category,
        custom_brand: draft.brand.trim() || null,
        custom_model: draft.model.trim() || null,
        // Sent in grams; the unit picker is only for typing.
        weight_override: draft.weight.trim() ? { value: String(gramsFromInput(draft.weight, draft.weightUnit)), unit: "g" as const } : null,
        notes: draft.notes.trim() || null,
        ...(imagePath ? { image_path: imagePath } : {}),
      };
      const saved = replacing
        ? await updateMyGear(replacing.id, { ...payload, product_id: null })
        : await addMyGear({ ...payload, client_request_id: requestId });
      onSaved(saved);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't save. Try again.");
      setSaving(false);
      onBusyChange(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className={styles.customForm}>
      <label className={ui.field}>
        <span className={ui.label}>Name</span>
        <input
          className={ui.input}
          value={draft.name}
          onChange={(event) => update({ name: event.target.value })}
          placeholder={`e.g. My old ${slot.noun}`}
          maxLength={120}
          aria-invalid={Boolean(errors.name)}
          autoFocus
        />
        {errors.name && <span className={ui.fieldError}>{errors.name}</span>}
      </label>

      {categoryOptions.length > 1 && (
        <label className={ui.field}>
          <span className={ui.label}>Type</span>
          <select className={ui.input} value={draft.category} onChange={(event) => update({ category: event.target.value })}>
            {categoryOptions.map((slug) => (
              <option key={slug} value={slug}>
                {categoryNames[slug] ?? slug}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className={ui.row}>
        <label className={ui.field}>
          <span className={ui.label}>Brand (optional)</span>
          <input className={ui.input} value={draft.brand} maxLength={80} onChange={(event) => update({ brand: event.target.value })} />
        </label>
        <label className={ui.field}>
          <span className={ui.label}>Model (optional)</span>
          <input className={ui.input} value={draft.model} maxLength={80} onChange={(event) => update({ model: event.target.value })} />
        </label>
      </div>

      <div className={ui.field}>
        <label className={ui.label} htmlFor="custom-weight">
          Weight each (optional)
        </label>
        <div className={ui.inline}>
          <input
            id="custom-weight"
            className={ui.input}
            type="number"
            inputMode="decimal"
            min={0}
            step="any"
            value={draft.weight}
            onChange={(event) => update({ weight: event.target.value })}
            aria-invalid={Boolean(errors.weight)}
          />
          <select
            className={`${ui.input} ${styles.unit}`}
            value={draft.weightUnit}
            aria-label="Weight unit"
            onChange={(event) => update({ weightUnit: event.target.value as WeightUnit })}
          >
            {WEIGHT_INPUT_UNITS[units].map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
        </div>
        {errors.weight && <span className={ui.fieldError}>{errors.weight}</span>}
      </div>

      <label className={ui.field}>
        <span className={ui.label}>Notes (optional)</span>
        <textarea
          className={ui.input}
          rows={2}
          maxLength={2000}
          value={draft.notes}
          onChange={(event) => update({ notes: event.target.value })}
        />
      </label>

      {isSignedIn && (
        <label className={ui.field}>
          <span className={ui.label}>Photo (optional)</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
          />
          <span className={ui.hint}>JPEG, PNG or WebP up to 5 MB. Only you can see it.</span>
          {errors.photo && <span className={ui.fieldError}>{errors.photo}</span>}
        </label>
      )}

      {error && (
        <p className={ui.error} role="alert">
          {error}
        </p>
      )}
      {needsAuth && (
        <div className={ui.notice} role="status">
          <p>
            <strong>Sign in to save your gear.</strong>{" "}We&apos;ll keep what you&apos;ve entered.
          </p>
          <div className={styles.authActions}>
            <Link href={`/signup${nextQuery("/gear?resume=1")}`} className={ui.primary}>
              Create account
            </Link>
            <Link href={`/login${nextQuery("/gear?resume=1")}`} className={ui.secondary}>
              Sign in
            </Link>
          </div>
        </div>
      )}

      <div className={styles.customActions}>
        <button type="button" className={ui.ghost} onClick={onBack} disabled={saving}>
          ← Back to products
        </button>
        <button type="submit" className={ui.primary} disabled={saving}>
          {saving ? "Saving…" : replacing ? "Replace with custom item" : "Add to my gear"}
        </button>
      </div>
    </form>
  );
}
