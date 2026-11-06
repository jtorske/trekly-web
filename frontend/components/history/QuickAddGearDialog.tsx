"use client";

import { useRef, useState } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { addMyGear, type ProductSummary } from "@/lib/gearApi";
import { toast } from "@/lib/toast";
import QuickAddGear from "./QuickAddGear";
import styles from "./history.module.css";

/**
 * "Quick-add gear" on the gear page: onboarding's "What's in your pack?" in a
 * dialog. Each pick keeps one request id for the dialog's life, so a retry
 * after a failure adds nothing twice.
 */
export default function QuickAddGearDialog({
  owned,
  onAdded,
  onClose,
}: {
  owned: ReadonlySet<string>;
  /** Called after any item was added, so the page can reload its gear. */
  onAdded: () => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState<Map<string, ProductSummary>>(new Map());
  const [busy, setBusy] = useState(false);
  const requestIds = useRef(new Map<string, string>());
  const added = useRef(new Set<string>());

  const toggle = (product: ProductSummary) =>
    setSelected((current) => {
      const next = new Map(current);
      if (next.has(product.id)) next.delete(product.id);
      else next.set(product.id, product);
      return next;
    });

  const add = async () => {
    setBusy(true);
    const products = [...selected.values()].filter((product) => !added.current.has(product.id));
    try {
      for (const product of products) {
        let requestId = requestIds.current.get(product.id);
        if (!requestId) {
          requestId = crypto.randomUUID();
          requestIds.current.set(product.id, requestId);
        }
        await addMyGear({ product_id: product.id, client_request_id: requestId });
        added.current.add(product.id);
      }
      onAdded();
      const count = selected.size;
      toast.success(count === 1 ? "1 item added to your gear" : `${count} items added to your gear`);
      onClose();
    } catch (caught) {
      if (added.current.size > 0) onAdded();
      toast.failure("add the rest of your gear", caught, () => void add());
      setBusy(false);
    }
  };

  const count = selected.size;
  return (
    <Dialog
      title="Quick-add gear"
      subtitle="Tap what's in your pack. You can add sizes and weights later."
      size="lg"
      sheet
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <span className={styles.footerNote}>{count === 0 ? "Nothing picked yet." : `${count} picked`}</span>
          <button type="button" className={ui.secondary} onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className={ui.primary} onClick={() => void add()} disabled={busy || count === 0}>
            {busy ? "Adding…" : count === 1 ? "Add 1 item" : count === 0 ? "Add items" : `Add ${count} items`}
          </button>
        </>
      }
    >
      <QuickAddGear owned={owned} selected={selected} onToggle={toggle} />
    </Dialog>
  );
}
