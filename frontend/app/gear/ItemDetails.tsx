"use client";

import { useState, type FormEvent } from "react";
import Dialog from "@/components/Dialog";
import GearThumb from "@/components/GearThumb";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import {
  deleteMyGear,
  updateMyGear,
  type Condition,
  type GearItem,
  type GearItemInput,
  type WeightUnit,
} from "@/lib/gearApi";
import { removeImages, uploadImage, validateImage } from "@/lib/storage";
import { formatCapacity, formatSpecValue, formatWeight, WEIGHT_BASIS_LABELS, type UnitSystem } from "@/lib/units";
import type { Slot } from "./slots";
import styles from "./ItemDetails.module.css";

const CONDITIONS: { value: Condition; label: string }[] = [
  { value: "new", label: "New" },
  { value: "good", label: "Good" },
  { value: "worn", label: "Worn" },
  { value: "needs_repair", label: "Needs repair" },
  { value: "retired", label: "Retired" },
];

const GRAMS_PER: Record<WeightUnit, number> = { g: 1, kg: 1000, oz: 28.349523125, lb: 453.59237 };

function overrideInUnit(grams: number, unit: WeightUnit): string {
  // Show what the user typed: 12.5 oz is stored as 354.369 g and round-trips to 12.5.
  return String(Number((grams / GRAMS_PER[unit]).toFixed(unit === "g" ? 1 : 3)));
}

export default function ItemDetails({
  item,
  slot,
  categoryNames,
  userId,
  units,
  onSaved,
  onDeleted,
  onReplace,
  onClose,
}: {
  item: GearItem;
  slot: Slot;
  categoryNames: Record<string, string>;
  userId: string;
  units: UnitSystem;
  onSaved: (item: GearItem) => void;
  onDeleted: (item: GearItem) => void;
  onReplace: (item: GearItem) => void;
  onClose: () => void;
}) {
  const isCustom = item.kind === "custom";
  const [name, setName] = useState(item.custom_name ?? "");
  const [category, setCategory] = useState(item.category.slug);
  const [brand, setBrand] = useState(item.custom_brand ?? "");
  const [model, setModel] = useState(item.custom_model ?? "");
  const [quantity, setQuantity] = useState(String(item.quantity));
  const overrideUnit = item.weight.override_unit ?? (units === "metric" ? "g" : "oz");
  const [weightUnit, setWeightUnit] = useState<WeightUnit>(overrideUnit);
  const [weight, setWeight] = useState(
    item.weight.override_g != null ? overrideInUnit(item.weight.override_g, overrideUnit) : "",
  );
  const [notes, setNotes] = useState(item.notes ?? "");
  const [condition, setCondition] = useState<Condition | "">(item.condition ?? "");
  const [photo, setPhoto] = useState<File | null>(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const manufacturerWeight = item.weight.manufacturer_g;
  const specs = item.variant?.specs.length ? item.variant.specs : item.product?.key_specs ?? [];

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty < 1 || qty > 99) nextErrors.quantity = "Enter a whole number from 1 to 99.";
    if (weight.trim() && !(Number(weight) >= 0)) nextErrors.weight = "Enter a positive number.";
    if (isCustom && !name.trim()) nextErrors.name = "Give your item a name.";
    if (photo) {
      const problem = validateImage(photo, "gear-photos");
      if (problem) nextErrors.photo = problem;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    setBusy(true);
    setError(null);
    let uploaded: string | null = null;
    try {
      const update: GearItemInput = {
        quantity: qty,
        weight_override: weight.trim() ? { value: weight.trim(), unit: weightUnit } : null,
        notes: notes.trim() || null,
        condition: condition || null,
      };
      if (isCustom) {
        update.custom_name = name.trim();
        update.custom_brand = brand.trim() || null;
        update.custom_model = model.trim() || null;
        update.category = category;
      }
      if (photo) {
        uploaded = await uploadImage("gear-photos", userId, photo);
        update.image_path = uploaded;
      } else if (removePhoto) {
        update.image_path = null;
      }
      const saved = await updateMyGear(item.id, update);
      // Clean up the replaced photo only after the item points at the new one.
      if (item.image_path && item.image_path !== saved.image_path) {
        removeImages("gear-photos", [item.image_path]).catch(() => undefined);
      }
      onSaved(saved);
    } catch (caught) {
      if (uploaded) removeImages("gear-photos", [uploaded]).catch(() => undefined);
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "That didn't save.");
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteMyGear(item.id);
      if (item.image_path) removeImages("gear-photos", [item.image_path]).catch(() => undefined);
      onDeleted(item);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't delete. Try again.");
      setBusy(false);
      setConfirmingDelete(false);
    }
  };

  return (
    <Dialog
      title={item.display_name}
      subtitle={
        <>
          {slot.label}
          {item.kind === "custom" ? " · Custom item" : item.product?.status === "discontinued" ? " · Discontinued model" : ""}
        </>
      }
      onClose={onClose}
      busy={busy}
      footer={
        confirmingDelete ? (
          <div className={styles.confirmDelete} role="alertdialog" aria-label="Confirm removal">
            <span>Remove this from your gear? The catalogue product isn&apos;t affected.</span>
            <button type="button" className={ui.secondary} onClick={() => setConfirmingDelete(false)} disabled={busy}>
              Keep it
            </button>
            <button type="button" className={ui.danger} onClick={remove} disabled={busy}>
              {busy ? "Removing…" : "Remove"}
            </button>
          </div>
        ) : (
          <>
            <button type="button" className={ui.ghost} onClick={() => setConfirmingDelete(true)} disabled={busy}>
              Remove from my gear
            </button>
            <button type="button" className={ui.secondary} onClick={() => onReplace(item)} disabled={busy}>
              Replace…
            </button>
            <button type="submit" form="item-details-form" className={ui.primary} disabled={busy}>
              {busy ? "Saving…" : "Save changes"}
            </button>
          </>
        )
      }
    >
      <div className={styles.summary}>
        <GearThumb
          icon={slot.icon}
          productImage={item.product?.image}
          photoPath={removePhoto ? null : item.image_path}
          alt={item.display_name}
          size="lg"
        />
        <dl className={styles.facts}>
          <div>
            <dt>Manufacturer weight</dt>
            <dd>
              {manufacturerWeight != null
                ? `${formatWeight(manufacturerWeight, units)} (${WEIGHT_BASIS_LABELS[item.weight.manufacturer_basis ?? ""] ?? "listed"})`
                : isCustom
                  ? "—"
                  : "Not published"}
            </dd>
          </div>
          {item.capacity.effective_ml != null && (
            <div>
              <dt>Capacity</dt>
              <dd>{formatCapacity(item.capacity.effective_ml, units)}</dd>
            </div>
          )}
          {specs.slice(0, 4).map((spec) => (
            <div key={spec.key}>
              <dt>{spec.label}</dt>
              <dd>{formatSpecValue(spec.value, spec.unit, units)}</dd>
            </div>
          ))}
        </dl>
      </div>

      <form id="item-details-form" className={styles.form} onSubmit={save} noValidate>
        {isCustom && (
          <>
            <label className={ui.field}>
              <span className={ui.label}>Name</span>
              <input className={ui.input} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} aria-invalid={Boolean(errors.name)} />
              {errors.name && <span className={ui.fieldError}>{errors.name}</span>}
            </label>
            <div className={ui.row}>
              <label className={ui.field}>
                <span className={ui.label}>Brand</span>
                <input className={ui.input} value={brand} maxLength={80} onChange={(e) => setBrand(e.target.value)} />
              </label>
              <label className={ui.field}>
                <span className={ui.label}>Model</span>
                <input className={ui.input} value={model} maxLength={80} onChange={(e) => setModel(e.target.value)} />
              </label>
              {slot.categories.length > 1 && (
                <label className={ui.field}>
                  <span className={ui.label}>Type</span>
                  <select className={ui.input} value={category} onChange={(e) => setCategory(e.target.value)}>
                    {!slot.categories.includes(category) && <option value={category}>{item.category.name}</option>}
                    {slot.categories.map((slug) => (
                      <option key={slug} value={slug}>
                        {categoryNames[slug] ?? slug}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </>
        )}

        <div className={ui.row}>
          <label className={ui.field}>
            <span className={ui.label}>Quantity</span>
            <input
              className={ui.input}
              type="number"
              min={1}
              max={99}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              aria-invalid={Boolean(errors.quantity)}
            />
            {errors.quantity && <span className={ui.fieldError}>{errors.quantity}</span>}
          </label>
          <label className={ui.field}>
            <span className={ui.label}>Condition</span>
            <select className={ui.input} value={condition} onChange={(e) => setCondition(e.target.value as Condition | "")}>
              <option value="">Not set</option>
              {CONDITIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={ui.field}>
          <label className={ui.label} htmlFor="item-weight">
            {isCustom ? "Weight each" : "Your measured weight (optional)"}
          </label>
          <div className={ui.inline}>
            <input
              id="item-weight"
              className={ui.input}
              type="number"
              inputMode="decimal"
              min={0}
              step="any"
              value={weight}
              placeholder={isCustom ? "" : "Use manufacturer weight"}
              onChange={(e) => setWeight(e.target.value)}
              aria-invalid={Boolean(errors.weight)}
            />
            <select
              className={`${ui.input} ${styles.unit}`}
              value={weightUnit}
              aria-label="Weight unit"
              onChange={(e) => setWeightUnit(e.target.value as WeightUnit)}
            >
              <option value="oz">oz</option>
              <option value="lb">lb</option>
              <option value="g">g</option>
              <option value="kg">kg</option>
            </select>
          </div>
          {!isCustom && (
            <span className={ui.hint}>
              {item.weight.source === "override"
                ? "Your weight is used instead of the manufacturer's. Clear it to go back."
                : "Leave blank to use the manufacturer's figure."}
            </span>
          )}
          {errors.weight && <span className={ui.fieldError}>{errors.weight}</span>}
        </div>

        <label className={ui.field}>
          <span className={ui.label}>Notes</span>
          <textarea className={ui.input} rows={2} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>

        <div className={ui.field}>
          <span className={ui.label}>Your photo</span>
          <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          {item.image_path && !photo && (
            <label className={styles.checkbox}>
              <input type="checkbox" checked={removePhoto} onChange={(e) => setRemovePhoto(e.target.checked)} /> Remove current photo
            </label>
          )}
          <span className={ui.hint}>JPEG, PNG or WebP up to 5 MB. Only you can see it.</span>
          {errors.photo && <span className={ui.fieldError}>{errors.photo}</span>}
        </div>

        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
