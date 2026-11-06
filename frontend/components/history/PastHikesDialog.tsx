"use client";

import { useState } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { undatedLabel } from "@/lib/hikeDate";
import type { PastHikesResult } from "@/lib/hikeLogsApi";
import type { PickerPreferences } from "@/lib/pastHikes";
import { toast } from "@/lib/toast";
import type { TrailListItem } from "@/lib/trailsApi";
import PastHikesPicker from "./PastHikesPicker";
import styles from "./history.module.css";

/**
 * "Add past hikes" from the journal: the onboarding picker in a dialog, for
 * hikers who skipped that step or remember more later. Nothing is saved
 * until they press Add.
 */
export default function PastHikesDialog({
  catalogue,
  logged,
  joinedAt,
  preferences,
  onAdd,
  onClose,
}: {
  catalogue: TrailListItem[];
  logged: ReadonlySet<string>;
  joinedAt: string | null;
  preferences?: PickerPreferences;
  onAdd: (trailIds: string[]) => Promise<PastHikesResult>;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const toggle = (trailId: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(trailId)) next.delete(trailId);
      else next.add(trailId);
      return next;
    });

  const add = async () => {
    setBusy(true);
    try {
      const { added } = await onAdd([...selected]);
      toast.success(
        added.length === 1 ? "1 hike added to your journal" : `${added.length} hikes added to your journal`,
        { link: { label: "Open journal", href: "/journal" } },
      );
      onClose();
    } catch (caught) {
      toast.failure("add your hikes", caught, () => void add());
      setBusy(false);
    }
  };

  const count = selected.size;
  return (
    <Dialog
      title="Add past hikes"
      subtitle="Tap the trails you've hiked before."
      size="lg"
      sheet
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <span className={styles.footerNote}>They&apos;ll show as &ldquo;{undatedLabel(joinedAt)}&rdquo;. Add a date to any of them later.</span>
          <button type="button" className={ui.secondary} onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className={ui.primary} onClick={() => void add()} disabled={busy || count === 0}>
            {busy ? "Adding…" : count === 0 ? "Add hikes" : count === 1 ? "Add 1 hike" : `Add ${count} hikes`}
          </button>
        </>
      }
    >
      <PastHikesPicker catalogue={catalogue} logged={logged} selected={selected} onToggle={toggle} preferences={preferences} />
    </Dialog>
  );
}
