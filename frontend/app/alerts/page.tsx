"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Dialog from "@/components/Dialog";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { alertsApi, type CampgroundAlert } from "@/lib/availabilityApi";
import { SUMMARY_LABELS, formatStay, sentence } from "@/lib/stay";
import profile from "@/app/profile/page.module.css";
import styles from "./page.module.css";

const STATUS_LABELS: Record<CampgroundAlert["status"], string> = {
  active: "Watching",
  notified: "Opened up",
  cancelled: "Cancelled",
  expired: "Dates passed",
};

const WHEN = new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function AlertCard({
  alert,
  busy,
  onCancel,
  onRearm,
  onRemove,
}: {
  alert: CampgroundAlert;
  busy: boolean;
  onCancel: () => void;
  onRearm: () => void;
  onRemove: () => void;
}) {
  const name = alert.site_code && alert.site_code !== alert.campground
    ? `${alert.campground} ${alert.site_code}`
    : alert.campground;
  let detail: string | null = null;
  if (alert.status === "notified" && alert.notified_at) {
    detail = `${sentence(`We emailed you on ${WHEN.format(new Date(alert.notified_at))}`)} If it's gone, turn the alert back on.`;
  } else if (alert.status === "active") {
    detail = alert.last_checked_at && alert.last_summary
      ? `Last checked ${WHEN.format(new Date(alert.last_checked_at))}: ${SUMMARY_LABELS[alert.last_summary].toLowerCase()}.`
      : "Not checked yet. We check every few minutes.";
  }

  return (
    <li className={`${styles.card} ${alert.status === "active" || alert.status === "notified" ? "" : styles.inactive}`}>
      <div className={styles.cardHead}>
        <div>
          <h2 className={styles.campground}>{name}</h2>
          <p className={styles.meta}>
            {[alert.park, alert.trail?.name].filter(Boolean).join(" · ")}
          </p>
        </div>
        <span className={`${styles.status} ${styles[`status_${alert.status}`]}`}>{STATUS_LABELS[alert.status]}</span>
      </div>
      <p className={styles.stay}>
        {formatStay(alert.start_date, alert.nights)} · party of {alert.party_size}
      </p>
      {detail && <p className={styles.detail}>{detail}</p>}
      <div className={styles.actions}>
        {alert.trail && (
          <Link
            href={`/trails?${new URLSearchParams({
              id: alert.trail.id,
              start: alert.start_date,
              nights: String(alert.nights),
              party: String(alert.party_size),
            })}`}
            className={ui.ghost}
          >
            Check now
          </Link>
        )}
        {alert.status === "notified" && (
          <button type="button" className={ui.secondary} onClick={onRearm} disabled={busy}>
            Turn back on
          </button>
        )}
        {alert.status === "active" || alert.status === "notified" ? (
          <button type="button" className={ui.ghost} onClick={onCancel} disabled={busy}>
            Cancel alert
          </button>
        ) : (
          <button type="button" className={ui.ghost} onClick={onRemove} disabled={busy}>
            Remove
          </button>
        )}
      </div>
    </li>
  );
}

function AlertsContent() {
  const [alerts, setAlerts] = useState<CampgroundAlert[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<CampgroundAlert | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    alertsApi
      .list(signal)
      .then((found) => {
        setAlerts(found);
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        setLoadError(error instanceof ApiError ? error.message : "We couldn't load your alerts.");
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const act = async (alert: CampgroundAlert, action: () => Promise<CampgroundAlert | void>) => {
    setBusyId(alert.id);
    setActionError(null);
    try {
      const updated = await action();
      setAlerts((current) =>
        updated
          ? (current ?? []).map((a) => (a.id === alert.id ? updated : a))
          : (current ?? []).filter((a) => a.id !== alert.id),
      );
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "That didn't work. Try again.");
    } finally {
      setBusyId(null);
    }
  };

  let body;
  if (loadError) {
    body = (
      <p className={ui.error} role="alert">
        {loadError}{" "}
        <button type="button" className={ui.ghost} onClick={() => load()}>
          Try again
        </button>
      </p>
    );
  } else if (alerts === null) {
    body = <div className={`${ui.skeleton} ${styles.skeleton}`} aria-label="Loading" />;
  } else if (alerts.length === 0) {
    body = (
      <div className={styles.empty}>
        <h2 className={styles.emptyTitle}>No alerts yet</h2>
        <p>
          On an overnight trail, check availability for your dates. If a campground is full, choose
          &ldquo;Alert me&rdquo; and we&apos;ll email you when it opens up.
        </p>
        <Link href="/trail-list" className={ui.primary}>
          Explore trails
        </Link>
      </div>
    );
  } else {
    body = (
      <ul className={styles.list}>
        {alerts.map((alert) => (
          <AlertCard
            key={alert.id}
            alert={alert}
            busy={busyId === alert.id}
            onCancel={() => setConfirming(alert)}
            onRearm={() => act(alert, () => alertsApi.rearm(alert.id))}
            onRemove={() => act(alert, () => alertsApi.remove(alert.id))}
          />
        ))}
      </ul>
    );
  }

  return (
    <main className={profile.page}>
      <div className={profile.wrap}>
        <h1 className={profile.name}>Campground alerts</h1>
        <p className={profile.bio}>
          We email you once when every night of a stay opens up on Parks Canada. Trekly doesn&apos;t
          book for you.
        </p>
        {actionError && (
          <p className={ui.error} role="alert">
            {actionError}
          </p>
        )}
        <div className={styles.body}>{body}</div>
      </div>

      {confirming && (
        <Dialog
          title="Cancel this alert?"
          subtitle={`${confirming.campground} · ${formatStay(confirming.start_date, confirming.nights)}`}
          size="sm"
          busy={busyId === confirming.id}
          onClose={() => setConfirming(null)}
          footer={
            <>
              <button type="button" className={ui.ghost} onClick={() => setConfirming(null)}>
                Keep it
              </button>
              <button
                type="button"
                className={ui.danger}
                data-autofocus
                onClick={async () => {
                  const alert = confirming;
                  await act(alert, () => alertsApi.cancel(alert.id));
                  setConfirming(null);
                }}
              >
                Cancel alert
              </button>
            </>
          }
        >
          <p>We&apos;ll stop checking and won&apos;t email you about these dates.</p>
        </Dialog>
      )}
    </main>
  );
}

export default function AlertsPage() {
  return (
    <Suspense fallback={<main className={profile.page} />}>
      <RequireAuth fallback={<main className={profile.page} aria-busy="true" />}>
        <AlertsContent />
      </RequireAuth>
    </Suspense>
  );
}
