"use client";

import { useState, type FormEvent } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { alertsApi, type CampgroundAlert, type Stay } from "@/lib/availabilityApi";
import { formatStay } from "@/lib/stay";
import { formProblem, toast } from "@/lib/toast";
import { alertPlace } from "./alertGroups";
import StayFields from "./StayFields";

/** New dates or party size for an alert; it starts watching again. */
export default function EditStayDialog({
  alert,
  today,
  onSaved,
  onClose,
}: {
  alert: CampgroundAlert;
  today: string;
  onSaved: (alert: CampgroundAlert) => void;
  onClose: () => void;
}) {
  // A past stay can't be watched again as it is, so it starts from today.
  const [stay, setStay] = useState<Stay>({
    start: alert.start_date < today ? today : alert.start_date,
    nights: alert.nights,
    party: alert.party_size,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const watching = alert.status === "active";

  const save = async (event?: FormEvent) => {
    event?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await alertsApi.update(alert.id, {
        start_date: stay.start,
        nights: stay.nights,
        party_size: stay.party,
      });
      toast.success(watching ? "Alert dates updated" : "Watching your new dates");
      onSaved(saved);
    } catch (caught) {
      const problem = formProblem(caught);
      if (problem) setError(problem);
      else toast.failure("change the dates", caught, () => void save());
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={watching ? "Edit dates" : "Watch new dates"}
      subtitle={
        <>
          <strong>{alertPlace(alert)}</strong> · now {formatStay(alert.start_date, alert.nights)}
        </>
      }
      size="sm"
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <button type="button" className={ui.ghost} onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" form="edit-stay" className={ui.primary} disabled={busy} data-autofocus>
            {busy ? "Saving…" : watching ? "Save dates" : "Start watching"}
          </button>
        </>
      }
    >
      <form id="edit-stay" onSubmit={save}>
        <StayFields stay={stay} today={today} onChange={setStay} />
        <p className={ui.hint}>
          We&apos;ll start checking again from scratch and email you once when every night is available.
        </p>
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
