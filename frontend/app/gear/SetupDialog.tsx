"use client";

import { useState, type FormEvent } from "react";
import Dialog from "@/components/Dialog";
import GearThumb from "@/components/GearThumb";
import { matImage } from "@/lib/gearImage";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import type { GearItem } from "@/lib/gearApi";
import { createSetup, deleteSetup, updateSetup, type GearSetup } from "@/lib/setupsApi";
import { slotForItem } from "./slots";
import styles from "./SetupDialog.module.css";

/** Create or edit a named setup from gear the user already owns. */
export default function SetupDialog({
  items,
  setup,
  onSaved,
  onDeleted,
  onClose,
}: {
  items: GearItem[];
  setup: GearSetup | null;
  onSaved: (setup: GearSetup) => void;
  onDeleted: (id: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(setup?.name ?? "");
  const [description, setDescription] = useState(setup?.description ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set(setup?.items.map((item) => item.id) ?? []));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // Core gear first, so the main kit is quick to pick.
  const ordered = [...items].sort((a, b) => Number(Boolean(slotForItem(b).core)) - Number(Boolean(slotForItem(a).core)));

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Give your setup a name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Keep the mat's order so the setup reads like the flat lay.
      const itemIds = ordered.filter((item) => selected.has(item.id)).map((item) => item.id);
      const input = { name: name.trim(), description: description.trim() || null, item_ids: itemIds };
      const saved = setup ? await updateSetup(setup.id, input) : await createSetup(input);
      onSaved(saved);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "That didn't save. Try again.");
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!setup) return;
    setBusy(true);
    try {
      await deleteSetup(setup.id);
      onDeleted(setup.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't delete.");
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={setup ? "Edit setup" : "Create a setup"}
      subtitle="Group the gear you take together — e.g. “Ultralight 2-Night Kit”. Items stay in your gear; a setup just references them."
      onClose={onClose}
      busy={busy}
      footer={
        confirmingDelete ? (
          <div className={styles.confirm} role="alertdialog" aria-label="Confirm delete setup">
            <span>Delete this setup? Your gear isn&apos;t affected.</span>
            <button type="button" className={ui.secondary} onClick={() => setConfirmingDelete(false)} disabled={busy}>
              Keep
            </button>
            <button type="button" className={ui.danger} onClick={remove} disabled={busy}>
              Delete setup
            </button>
          </div>
        ) : (
          <>
            {setup && (
              <button type="button" className={ui.ghost} onClick={() => setConfirmingDelete(true)} disabled={busy}>
                Delete setup
              </button>
            )}
            <button type="submit" form="setup-form" className={ui.primary} disabled={busy}>
              {busy ? "Saving…" : setup ? "Save setup" : "Create setup"}
            </button>
          </>
        )
      }
    >
      <form id="setup-form" className={styles.form} onSubmit={save} noValidate>
        <label className={ui.field}>
          <span className={ui.label}>Name</span>
          <input
            className={ui.input}
            value={name}
            maxLength={80}
            onChange={(event) => setName(event.target.value)}
            placeholder="Summer Rockies Backpacking Setup"
            autoFocus
          />
        </label>
        <label className={ui.field}>
          <span className={ui.label}>Note (optional)</span>
          <textarea
            className={ui.input}
            rows={2}
            maxLength={500}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Where and when you use it"
          />
        </label>
        <fieldset className={styles.items}>
          <legend className={ui.label}>
            Gear in this setup <span className={ui.hint}>({selected.size} selected)</span>
          </legend>
          {ordered.length === 0 ? (
            <p className={ui.hint}>Add gear to your mat first, then group it into setups.</p>
          ) : (
            ordered.map((item) => {
              const slot = slotForItem(item);
              return (
                <label key={item.id} className={styles.item}>
                  <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggle(item.id)} />
                  <GearThumb icon={slot.icon} productImage={matImage(item)} alt="" size="sm" />
                  <span className={styles.itemText}>
                    <span className={styles.itemName}>{item.display_name}</span>
                    <span className={ui.hint}>{slot.label}</span>
                  </span>
                </label>
              );
            })
          )}
        </fieldset>
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
