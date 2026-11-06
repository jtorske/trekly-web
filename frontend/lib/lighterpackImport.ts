import type { Carry, ProductSummary, WeightUnit } from "./gearApi";

/**
 * LighterPack import (backend app/routers/me_gear_import.py): the preview the
 * server proposes, the choices the hiker makes on it, and the confirm request
 * built from those choices. Nothing is added until the confirm request (lib/gearImportApi.ts).
 */

export type Confidence = "high" | "medium" | "low";

export interface ImportCandidate {
  product: ProductSummary;
  confidence: Confidence;
  score: number;
}

export interface ImportRow {
  index: number;
  name: string;
  lighterpack_category: string;
  description: string;
  quantity: number;
  weight: { value: number; unit: WeightUnit } | null;
  carry: Carry | null;
  match: ImportCandidate | null;
  alternatives: ImportCandidate[];
  /** Subcategory for adding it as the hiker's own item. */
  category: string;
  /** Proposed for import (food and fuel aren't). */
  include: boolean;
}

export interface ImportPreview {
  rows: ImportRow[];
  matched: number;
  unmatched: number;
}

/** "custom" adds it as the hiker's own item; otherwise a catalogue product id. */
export interface RowChoice {
  include: boolean;
  product: string | "custom";
  category: string;
}

export const MAX_FILE_BYTES = 500_000;

export interface ConfirmRequest {
  import_id: string;
  items: {
    index: number;
    product_id?: string;
    name?: string;
    category?: string;
    quantity: number;
    weight: { value: string; unit: WeightUnit } | null;
    carry: Carry | null;
    notes?: string | null;
  }[];
}

/** What each row starts as: the proposed match if there is one, else the hiker's own item. */
export function initialChoices(rows: ImportRow[]): Map<number, RowChoice> {
  return new Map(
    rows.map((row) => [row.index, { include: row.include, product: row.match?.product.id ?? "custom", category: row.category }]),
  );
}

/** Every product a row could be: the match first, then the alternatives. */
export function candidatesOf(row: ImportRow): ImportCandidate[] {
  return row.match ? [row.match, ...row.alternatives] : row.alternatives;
}

export function confirmRequest(importId: string, rows: ImportRow[], choices: Map<number, RowChoice>): ConfirmRequest {
  const items: ConfirmRequest["items"] = [];
  for (const row of rows) {
    const choice = choices.get(row.index);
    if (!choice?.include) continue;
    const weight = row.weight ? { value: String(row.weight.value), unit: row.weight.unit } : null;
    const base = { index: row.index, quantity: row.quantity, weight, carry: row.carry };
    if (choice.product === "custom") {
      items.push({ ...base, name: row.name, category: choice.category, notes: row.description || null });
    } else {
      items.push({ ...base, product_id: choice.product });
    }
  }
  return { import_id: importId, items };
}

export interface ImportCounts {
  included: number;
  catalogue: number;
  own: number;
  /** Included catalogue matches the hiker should look at (low confidence). */
  toCheck: number;
}

export function countChoices(rows: ImportRow[], choices: Map<number, RowChoice>): ImportCounts {
  const counts: ImportCounts = { included: 0, catalogue: 0, own: 0, toCheck: 0 };
  for (const row of rows) {
    const choice = choices.get(row.index);
    if (!choice?.include) continue;
    counts.included += 1;
    if (choice.product === "custom") {
      counts.own += 1;
      continue;
    }
    counts.catalogue += 1;
    const picked = candidatesOf(row).find((candidate) => candidate.product.id === choice.product);
    if (picked && picked.confidence === "low") counts.toCheck += 1;
  }
  return counts;
}

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "Strong match",
  medium: "Likely match",
  low: "Possible match: check it",
};
