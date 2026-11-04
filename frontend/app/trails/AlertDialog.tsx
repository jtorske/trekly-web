"use client";

import { useState } from "react";
import Link from "next/link";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { useAuth } from "@/components/AuthProvider";
import { alertsApi, type CampgroundAlert, type Stay } from "@/lib/availabilityApi";
import { nextQuery } from "@/lib/authLogic";
import { partyLimitProblem } from "@/lib/alertRules";
import { formatStay } from "@/lib/stay";
import { formProblem, toast } from "@/lib/toast";
import styles from "./AlertDialog.module.css";

/**
 * "Alert me when this opens up" for one campground and stay. Guests can open
 * it (the app is guest-first) and are asked to sign in only here; they come
 * back to the trail page with this dialog open again.
 */
export default function AlertDialog({
  trailId,
  siteId,
  campground,
  maxGroupSize = null,
  stay,
  returnTo,
  onCreated,
  onClose,
}: {
  trailId: string;
  siteId: string;
  campground: string;
  /** Parks Canada's maximum group size for the site, if it publishes one. */
  maxGroupSize?: number | null;
  stay: Stay;
  /** Trail page URL including the stay and `alert=<siteId>`, for after sign-in. */
  returnTo: string;
  /** After the alert is set (the alerts page adds it to its list). */
  onCreated?: (alert: CampgroundAlert) => void;
  onClose: () => void;
}) {
  const { status, user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await alertsApi.create({
        site_id: siteId,
        trail_id: trailId,
        start_date: stay.start,
        nights: stay.nights,
        party_size: stay.party,
      });
      // Already on the alerts page, there's no need to link to it.
      toast.success("Alert set. We'll email you if a site opens up", onCreated ? undefined : { link: { label: "View alerts", href: "/alerts" } });
      onCreated?.(created);
      onClose();
    } catch (caught) {
      const problem = formProblem(caught);
      if (problem) setError(problem);
      else toast.failure("set the alert", caught, () => void create());
      setBusy(false);
    }
  };

  const party = `party of ${stay.party}`;
  const tooMany = partyLimitProblem({ name: campground, max_group_size: maxGroupSize }, stay.party);
  let body;
  let footer;
  if (status === "signedIn") {
    body = (
      <>
        <p className={styles.lead}>
          We&apos;ll check Parks Canada about every 30 minutes and email{" "}
          <strong>{user?.email ?? "you"}</strong> once, as soon as every night is available.
        </p>
        <p className={ui.hint}>Trekly doesn&apos;t book for you, so act quickly when the email arrives.</p>
        {tooMany && (
          <p className={ui.error} role="alert">
            {tooMany} Change the party size to set an alert.
          </p>
        )}
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </>
    );
    footer = (
      <>
        <button type="button" className={ui.ghost} onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className={ui.primary} onClick={create} disabled={busy || Boolean(tooMany)} data-autofocus>
          {busy ? "Setting alert…" : "Set alert"}
        </button>
      </>
    );
  } else {
    body = (
      <p className={styles.lead}>
        Sign in and we&apos;ll email you as soon as every night of this stay opens up. Checking
        availability stays free without an account.
      </p>
    );
    footer = (
      <>
        <button type="button" className={ui.ghost} onClick={onClose}>
          Not now
        </button>
        <Link href={`/login${nextQuery(returnTo)}`} className={ui.primary} data-autofocus>
          Sign in to set alert
        </Link>
      </>
    );
  }

  return (
    <Dialog
      title="Alert me when this opens up"
      subtitle={
        <>
          <strong>{campground}</strong> · {formatStay(stay.start, stay.nights)} · {party}
        </>
      }
      onClose={onClose}
      busy={busy}
      size="sm"
      footer={footer}
    >
      {body}
    </Dialog>
  );
}
