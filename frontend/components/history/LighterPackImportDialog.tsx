"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { listCategories, type GearCategory } from "@/lib/gearApi";
import {
  CONFIDENCE_LABEL,
  MAX_FILE_BYTES,
  candidatesOf,
  confirmRequest,
  countChoices,
  initialChoices,
  type ImportPreview,
  type ImportRow,
  type RowChoice,
} from "@/lib/lighterpackImport";
import { confirmImport, previewImport } from "@/lib/gearImportApi";
import { formProblem, toast } from "@/lib/toast";
import { formatWeight, gramsFromInput } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import styles from "./LighterPackImport.module.css";
import shared from "./history.module.css";

/**
 * Import a LighterPack list on the gear page. Upload the CSV export, review
 * the proposed catalogue match for every item (with how sure it is), change
 * any of them or add it as your own item, then confirm. Nothing is added
 * before the confirm.
 */
export default function LighterPackImportDialog({ onAdded, onClose }: { onAdded: () => void; onClose: () => void }) {
  const fileId = useId();
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [choices, setChoices] = useState<Map<number, RowChoice>>(new Map());
  const [categories, setCategories] = useState<GearCategory[]>([]);
  const [busy, setBusy] = useState<"reading" | "adding" | null>(null);
  const [error, setError] = useState<string | null>(null);
  // One id per uploaded file, so retrying the confirm adds nothing twice.
  const importId = useRef<string>("");

  useEffect(() => {
    const controller = new AbortController();
    listCategories(controller.signal).then(setCategories).catch(() => undefined);
    return () => controller.abort();
  }, []);

  const read = async (file: File) => {
    setError(null);
    if (file.size > MAX_FILE_BYTES) {
      setError("That file is too big for a LighterPack list. Check you picked the CSV export.");
      return;
    }
    setBusy("reading");
    try {
      const result = await previewImport(await file.text());
      importId.current = crypto.randomUUID();
      setPreview(result);
      setChoices(initialChoices(result.rows));
    } catch (caught) {
      const problem = formProblem(caught);
      if (problem) setError(problem);
      else toast.failure("read that list", caught);
    } finally {
      setBusy(null);
    }
  };

  const add = async () => {
    if (!preview) return;
    setBusy("adding");
    setError(null);
    try {
      const result = await confirmImport(confirmRequest(importId.current, preview.rows, choices));
      onAdded();
      const total = result.added + result.already_added;
      toast.success(total === 1 ? "1 item added to your gear" : `${total} items added to your gear`);
      onClose();
    } catch (caught) {
      const problem = formProblem(caught);
      if (problem) setError(problem);
      else toast.failure("add your gear", caught, () => void add());
      setBusy(null);
    }
  };

  const counts = useMemo(() => (preview ? countChoices(preview.rows, choices) : null), [preview, choices]);
  const update = (index: number, change: Partial<RowChoice>) =>
    setChoices((current) => new Map(current).set(index, { ...current.get(index)!, ...change }));

  const footer = preview ? (
    <>
      <span className={shared.footerNote}>
        {counts!.catalogue} from the catalogue, {counts!.own} as your own
        {counts!.toCheck > 0 && <> · {counts!.toCheck} to check</>}
      </span>
      <button type="button" className={ui.secondary} onClick={() => setPreview(null)} disabled={busy !== null}>
        Choose another file
      </button>
      <button type="button" className={ui.primary} onClick={() => void add()} disabled={busy !== null || counts!.included === 0}>
        {busy === "adding" ? "Adding…" : counts!.included === 1 ? "Add 1 item" : `Add ${counts!.included} items`}
      </button>
    </>
  ) : (
    <button type="button" className={ui.secondary} onClick={onClose} disabled={busy !== null}>
      Cancel
    </button>
  );

  return (
    <Dialog
      title="Import from LighterPack"
      subtitle={preview ? "Check each match, then add them. Nothing's added until you do." : undefined}
      size="lg"
      sheet
      busy={busy !== null}
      onClose={onClose}
      footer={footer}
    >
      {!preview ? (
        <div className={styles.upload}>
          <ol className={styles.steps}>
            <li>In LighterPack, open the list you want.</li>
            <li>
              Choose <strong>Share</strong>, then <strong>Export to CSV</strong>.
            </li>
            <li>Upload the file here. We&apos;ll match each item to the gear catalogue for you to check.</li>
          </ol>
          <label htmlFor={fileId} className={`${ui.primary} ${styles.pick}`} aria-disabled={busy !== null}>
            {busy === "reading" ? "Reading your list…" : "Choose CSV file"}
          </label>
          <input
            id={fileId}
            type="file"
            accept=".csv,text/csv"
            className={ui.srOnly}
            disabled={busy !== null}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void read(file);
            }}
          />
        </div>
      ) : (
        <ul className={styles.rows} aria-label="Items in your list">
          {preview.rows.map((row) => (
            <ImportRowItem
              key={row.index}
              row={row}
              choice={choices.get(row.index)!}
              categories={categories}
              onChange={(change) => update(row.index, change)}
            />
          ))}
        </ul>
      )}
      {error && (
        <p className={ui.error} role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function ImportRowItem({
  row,
  choice,
  categories,
  onChange,
}: {
  row: ImportRow;
  choice: RowChoice;
  categories: GearCategory[];
  onChange: (change: Partial<RowChoice>) => void;
}) {
  const [units] = useUnits();
  const pickId = useId();
  const categoryId = useId();
  const candidates = candidatesOf(row);
  const picked = candidates.find((candidate) => candidate.product.id === choice.product) ?? null;
  const grams = row.weight ? gramsFromInput(String(row.weight.value), row.weight.unit) : null;
  const weight = grams != null ? formatWeight(grams, units) : null;
  const facts = [row.lighterpack_category, row.quantity > 1 ? `×${row.quantity}` : null, weight, row.carry]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className={`${styles.row} ${choice.include ? "" : styles.skipped}`}>
      <label className={styles.include}>
        <input type="checkbox" checked={choice.include} onChange={(event) => onChange({ include: event.target.checked })} />
        <span className={styles.rowName}>{row.name}</span>
      </label>
      <span className={styles.facts}>{facts}</span>

      {choice.include && (
        <div className={styles.choice}>
          <label className={ui.srOnly} htmlFor={pickId}>
            Add {row.name} as
          </label>
          <select id={pickId} className={ui.input} value={choice.product} onChange={(event) => onChange({ product: event.target.value })}>
            {candidates.map((candidate) => (
              <option key={candidate.product.id} value={candidate.product.id}>
                {candidate.product.display_name}
              </option>
            ))}
            <option value="custom">My own item: &ldquo;{row.name}&rdquo;</option>
          </select>
          {picked ? (
            <span className={`${styles.confidence} ${styles[picked.confidence]}`}>{CONFIDENCE_LABEL[picked.confidence]}</span>
          ) : (
            <>
              <label className={ui.srOnly} htmlFor={categoryId}>
                Category for {row.name}
              </label>
              <select
                id={categoryId}
                className={ui.input}
                value={choice.category}
                onChange={(event) => onChange({ category: event.target.value })}
              >
                {categories.length === 0 && <option value={choice.category}>{choice.category}</option>}
                {categories.map((group) => (
                  <optgroup key={group.slug} label={group.name}>
                    {group.subcategories.map((sub) => (
                      <option key={sub.slug} value={sub.slug}>
                        {sub.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </>
          )}
        </div>
      )}
    </li>
  );
}
