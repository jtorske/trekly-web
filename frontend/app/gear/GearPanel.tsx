"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  searchGearCatalog,
  type CatalogGearItem,
  type UserGearInput,
  type UserGearItem,
} from "@/lib/userGear";
import {
  CATALOG_CATEGORY_MAP,
  ESSENTIAL_SLOTS,
  GEAR_CATEGORIES,
  GENERIC_GEAR,
  SLOTS_BY_KEY,
  formatWeight,
  gramsToOunces,
  guessSlot,
  ouncesToGrams,
  type GearCategory,
} from "./gearCatalog";
import styles from "./GearPanel.module.css";

export interface GearDraft {
  category: GearCategory;
  slot: string | null;
  name: string;
  brand: string;
  model: string;
  weightOz: string;
  quantity: string;
  gearItemId: string | null;
}

export function emptyDraft(category: GearCategory, slot?: string): GearDraft {
  return {
    category,
    slot: slot ?? null,
    name: "",
    brand: "",
    model: "",
    weightOz: "",
    quantity: "1",
    gearItemId: null,
  };
}

export function draftFromItem(item: UserGearItem): GearDraft {
  return {
    category: item.category,
    slot: item.slot,
    name: item.name,
    brand: item.brand ?? "",
    model: item.model ?? "",
    weightOz: item.weight_g != null ? String(gramsToOunces(item.weight_g)) : "",
    quantity: String(item.quantity),
    gearItemId: item.gear_item_id,
  };
}

interface Suggestion {
  key: string;
  name: string;
  category: GearCategory;
  slot?: string;
  weightG: number | null;
  gearItemId: string | null;
  source: "catalogue" | "generic";
}

function fromCatalog(item: CatalogGearItem): Suggestion {
  const category = CATALOG_CATEGORY_MAP[item.category] ?? "accessories";
  return {
    key: `catalogue-${item.id}`,
    name: item.name,
    category,
    slot: guessSlot(item.name, category),
    weightG: item.weight_g,
    gearItemId: item.id,
    source: "catalogue",
  };
}

export function GearPanel({
  initialDraft,
  isEditing,
  isSignedIn,
  onSave,
  onDelete,
  onRequireAuth,
  onClose,
}: {
  initialDraft: GearDraft;
  isEditing: boolean;
  isSignedIn: boolean;
  onSave: (input: UserGearInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onRequireAuth: (draft: GearDraft) => void;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState(initialDraft);
  const [query, setQuery] = useState("");
  const [catalogResults, setCatalogResults] = useState<{
    query: string;
    items: CatalogGearItem[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  const trimmedQuery = query.trim();

  useEffect(() => {
    if (trimmedQuery.length < 2) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchGearCatalog(trimmedQuery)
        .then((items) => {
          if (!cancelled) setCatalogResults({ query: trimmedQuery, items });
        })
        .catch(() => {
          // The catalogue is a convenience; generic items still work without it.
          if (!cancelled) setCatalogResults({ query: trimmedQuery, items: [] });
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [trimmedQuery]);

  const suggestions = useMemo<Suggestion[]>(() => {
    const lower = trimmedQuery.toLowerCase();
    // Once an item has a name, only show suggestions for an explicit search.
    if (!lower && draft.name.trim()) return [];
    const generic = GENERIC_GEAR.filter((gear) =>
      lower
        ? gear.name.toLowerCase().includes(lower)
        : draft.slot
          ? gear.slot === draft.slot
          : gear.category === draft.category,
    ).map<Suggestion>((gear) => ({
      key: `generic-${gear.name}`,
      name: gear.name,
      category: gear.category,
      slot: gear.slot,
      weightG: gear.weightG,
      gearItemId: null,
      source: "generic",
    }));
    const catalogue =
      lower.length >= 2 && catalogResults?.query === trimmedQuery
        ? catalogResults.items.map(fromCatalog)
        : [];
    return [...catalogue, ...generic].slice(0, 8);
  }, [trimmedQuery, catalogResults, draft.slot, draft.category, draft.name]);

  const update = (patch: Partial<GearDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setNeedsAuth(false);
  };

  const applySuggestion = (suggestion: Suggestion) => {
    update({
      name: suggestion.name,
      category: suggestion.category,
      // Keep the slot the user opened the panel from; otherwise take the best guess.
      slot:
        draft.slot && SLOTS_BY_KEY[draft.slot]?.category === suggestion.category
          ? draft.slot
          : (suggestion.slot ?? null),
      weightOz: suggestion.weightG != null ? String(gramsToOunces(suggestion.weightG)) : "",
      gearItemId: suggestion.gearItemId,
    });
    setQuery("");
  };

  const categorySlots = ESSENTIAL_SLOTS.filter((slot) => slot.category === draft.category);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    const name = draft.name.trim();
    const quantity = Number(draft.quantity);
    const weightOz = draft.weightOz.trim() === "" ? null : Number(draft.weightOz);

    if (!name) return setError("Give this item a name.");
    if (!Number.isInteger(quantity) || quantity < 1) {
      return setError("Quantity must be a whole number of at least 1.");
    }
    if (weightOz !== null && (!Number.isFinite(weightOz) || weightOz < 0)) {
      return setError("Weight must be a positive number of ounces.");
    }

    if (!isSignedIn) {
      onRequireAuth(draft);
      setNeedsAuth(true);
      return;
    }

    setIsBusy(true);
    try {
      await onSave({
        category: draft.category,
        slot: draft.slot,
        name,
        brand: draft.brand.trim() || null,
        model: draft.model.trim() || null,
        weight_g: weightOz === null ? null : ouncesToGrams(weightOz),
        quantity,
        gear_item_id: draft.gearItemId,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Couldn't save this item.");
      setIsBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!onDelete) return;
    setIsBusy(true);
    setError(null);
    try {
      await onDelete();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Couldn't remove this item.");
      setIsBusy(false);
    }
  };

  const titleSlot = draft.slot ? SLOTS_BY_KEY[draft.slot]?.label : null;

  return (
    <dialog
      ref={dialogRef}
      className={styles.panel}
      aria-labelledby="gear-panel-title"
      onClose={onClose}
      onClick={(event) => {
        // Clicking the backdrop (the dialog element itself) closes the panel.
        if (event.target === event.currentTarget) dialogRef.current?.close();
      }}
    >
      <div className={styles.inner}>
        <header className={styles.header}>
          <h2 id="gear-panel-title" className={styles.title}>
            {isEditing ? "Edit gear" : `Add ${titleSlot?.toLowerCase() ?? "gear"}`}
          </h2>
          <button
            type="button"
            className={styles.close}
            onClick={() => dialogRef.current?.close()}
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className={styles.search}>
          <label className={styles.label} htmlFor="gear-search">
            Start from a common item
          </label>
          <input
            id="gear-search"
            className={styles.input}
            type="search"
            placeholder="Search gear, e.g. quilt, stove…"
            autoComplete="off"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {suggestions.length > 0 && (
            <ul className={styles.suggestions}>
              {suggestions.map((suggestion) => (
                <li key={suggestion.key}>
                  <button
                    type="button"
                    className={styles.suggestion}
                    onClick={() => applySuggestion(suggestion)}
                  >
                    <span>{suggestion.name}</span>
                    <span className={styles.suggestionMeta}>
                      {suggestion.weightG != null ? `~${formatWeight(suggestion.weightG)}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {trimmedQuery.length >= 2 && suggestions.length === 0 && (
            <p className={styles.hint}>No matches. Fill in the details below instead.</p>
          )}
        </div>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <label className={styles.field}>
            <span className={styles.label}>Name</span>
            <input
              className={styles.input}
              required
              value={draft.name}
              onChange={(event) => update({ name: event.target.value, gearItemId: null })}
              placeholder="e.g. Two-person tent"
            />
          </label>

          <div className={styles.row}>
            <label className={styles.field}>
              <span className={styles.label}>Category</span>
              <select
                className={styles.input}
                value={draft.category}
                onChange={(event) => {
                  const category = event.target.value as GearCategory;
                  update({
                    category,
                    slot:
                      draft.slot && SLOTS_BY_KEY[draft.slot]?.category === category
                        ? draft.slot
                        : null,
                  });
                }}
              >
                {GEAR_CATEGORIES.map((category) => (
                  <option key={category.key} value={category.key}>
                    {category.label}
                  </option>
                ))}
              </select>
            </label>

            {categorySlots.length > 0 && (
              <label className={styles.field}>
                <span className={styles.label}>Counts as</span>
                <select
                  className={styles.input}
                  value={draft.slot ?? ""}
                  onChange={(event) => update({ slot: event.target.value || null })}
                >
                  <option value="">Extra item</option>
                  {categorySlots.map((slot) => (
                    <option key={slot.key} value={slot.key}>
                      {slot.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <div className={styles.row}>
            <label className={styles.field}>
              <span className={styles.label}>Brand (optional)</span>
              <input
                className={styles.input}
                value={draft.brand}
                onChange={(event) => update({ brand: event.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Model (optional)</span>
              <input
                className={styles.input}
                value={draft.model}
                onChange={(event) => update({ model: event.target.value })}
              />
            </label>
          </div>

          <div className={styles.row}>
            <label className={styles.field}>
              <span className={styles.label}>Weight each (oz, optional)</span>
              <input
                className={styles.input}
                type="number"
                inputMode="decimal"
                min="0"
                step="0.1"
                value={draft.weightOz}
                onChange={(event) => update({ weightOz: event.target.value })}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Quantity</span>
              <input
                className={styles.input}
                type="number"
                inputMode="numeric"
                min="1"
                step="1"
                value={draft.quantity}
                onChange={(event) => update({ quantity: event.target.value })}
              />
            </label>
          </div>

          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}

          {needsAuth && (
            <div className={styles.authPrompt} role="status">
              <p>
                <strong>Log in to save your gear.</strong>{" "}
                We&apos;ll keep what
                you&apos;ve entered and bring you back here.
              </p>
              <div className={styles.authActions}>
                <Link href="/signup?next=/gear" className={styles.primaryButton}>
                  Sign up
                </Link>
                <Link href="/login?next=/gear" className={styles.secondaryButton}>
                  Log in
                </Link>
              </div>
            </div>
          )}

          <div className={styles.actions}>
            {onDelete &&
              (confirmingDelete ? (
                <span className={styles.confirmDelete}>
                  Remove this item?
                  <button
                    type="button"
                    className={styles.dangerButton}
                    onClick={handleDelete}
                    disabled={isBusy}
                  >
                    Remove
                  </button>
                  <button
                    type="button"
                    className={styles.textButton}
                    onClick={() => setConfirmingDelete(false)}
                  >
                    Keep
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className={styles.textButton}
                  onClick={() => setConfirmingDelete(true)}
                >
                  Remove item
                </button>
              ))}
            <span className={styles.spacer} />
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => dialogRef.current?.close()}
            >
              Cancel
            </button>
            <button type="submit" className={styles.primaryButton} disabled={isBusy}>
              {isBusy ? "Saving…" : isEditing ? "Save changes" : "Save to my gear"}
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
