"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { BellRing, CalendarDays, Clock, Plus, Users } from "lucide-react";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { alertsApi, type CampgroundAlert } from "@/lib/availabilityApi";
import { SUMMARY_LABELS, formatStay, localToday } from "@/lib/stay";
import { formProblem, toast } from "@/lib/toast";
import { removeWithUndo, reveal } from "@/lib/undo";
import { useHidden } from "@/lib/useHidden";
import { alertPlace, groupAlerts, timeAgo, type AlertGroupKey } from "./alertGroups";
import EditStayDialog from "./EditStayDialog";
import NewAlertDialog from "./NewAlertDialog";
import styles from "./page.module.css";

// The poller runs every 30 minutes (.github/workflows/alert-poller.yml), and
// GitHub can start scheduled runs late.
const CADENCE = "We check about every 30 minutes";

const SECTION_HINTS: Record<AlertGroupKey, string> = {
  active: "We email you once, as soon as every night of the stay is available.",
  found: "Every night opened up and we emailed you. Book soon: openings go quickly.",
  past: "Cancelled alerts and stays whose dates have passed.",
};

const cancelKey = (id: string) => `alert-cancel:${id}`;
const removeKey = (id: string) => `alert:${id}`;

function chip(alert: CampgroundAlert, group: AlertGroupKey): { label: string; tone: string } {
  if (alert.status === "cancelled") return { label: "Cancelled", tone: "muted" };
  if (group === "past") return { label: alert.status === "notified" ? "Found" : "Ended", tone: "muted" };
  return alert.status === "notified" ? { label: "Found", tone: "found" } : { label: "Watching", tone: "active" };
}

function detail(alert: CampgroundAlert, group: AlertGroupKey, now: Date): string {
  if (alert.status === "cancelled") return "Cancelled. We stopped checking these dates.";
  if (group === "past") {
    return alert.status === "notified"
      ? "These dates have passed."
      : "The dates passed without every night opening up.";
  }
  if (alert.status === "notified") {
    return alert.notified_at ? `Found ${timeAgo(alert.notified_at, now)}. If it's gone, turn the alert back on.` : "Found.";
  }
  if (!alert.last_checked_at) return `Not checked yet. ${CADENCE}.`;
  const result = alert.last_summary ? `: ${SUMMARY_LABELS[alert.last_summary].toLowerCase()}` : "";
  return `Last checked ${timeAgo(alert.last_checked_at, now)}${result}.`;
}

function AlertCard({
  alert,
  group,
  now,
  checking,
  busy,
  onCheck,
  onEdit,
  onCancel,
  onRearm,
  onRemove,
}: {
  alert: CampgroundAlert;
  group: AlertGroupKey;
  now: Date;
  checking: boolean;
  busy: boolean;
  onCheck: () => void;
  onEdit: () => void;
  onCancel: () => void;
  onRearm: () => void;
  onRemove: () => void;
}) {
  const status = chip(alert, group);
  const where = [alert.park, alert.trail?.name].filter(Boolean).join(" · ");
  return (
    <li className={styles.card} data-group={group}>
      <div className={styles.cardHead}>
        <div className={styles.cardTitle}>
          <h3 className={styles.campground}>{alertPlace(alert)}</h3>
          {where && <p className={styles.where}>{where}</p>}
        </div>
        <span className={styles.chip} data-tone={status.tone}>
          {status.label}
        </span>
      </div>

      <ul className={styles.facts}>
        <li>
          <CalendarDays aria-hidden="true" className={styles.factIcon} />
          {formatStay(alert.start_date, alert.nights)}
        </li>
        <li>
          <Users aria-hidden="true" className={styles.factIcon} />
          Party of {alert.party_size}
        </li>
      </ul>

      <p className={styles.detail}>
        {group === "active" && <Clock aria-hidden="true" className={styles.factIcon} />}
        {detail(alert, group, now)}
      </p>

      <div className={styles.actions}>
        {group === "active" && (
          <>
            <button type="button" className={ui.secondary} onClick={onCheck} disabled={busy || checking}>
              {checking ? "Checking…" : "Check now"}
            </button>
            <button type="button" className={ui.ghost} onClick={onEdit} disabled={busy}>
              Edit dates
            </button>
            <button type="button" className={ui.ghost} onClick={onCancel} disabled={busy}>
              Cancel
            </button>
          </>
        )}
        {group === "found" && (
          <>
            {alert.booking_url && (
              <a href={alert.booking_url} target="_blank" rel="noopener noreferrer" className={ui.primary}>
                Book on Parks Canada <span aria-hidden="true">↗</span>
              </a>
            )}
            <button type="button" className={ui.secondary} onClick={onRearm} disabled={busy}>
              Turn back on
            </button>
            <button type="button" className={ui.ghost} onClick={onEdit} disabled={busy}>
              Edit dates
            </button>
            <button type="button" className={ui.ghost} onClick={onCancel} disabled={busy}>
              Cancel
            </button>
          </>
        )}
        {group === "past" && (
          <>
            <button type="button" className={ui.secondary} onClick={onEdit} disabled={busy}>
              Watch new dates
            </button>
            <button type="button" className={ui.ghost} onClick={onRemove} disabled={busy}>
              Remove
            </button>
          </>
        )}
      </div>
    </li>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className={styles.empty}>
      <span className={styles.emptyIcon} aria-hidden="true">
        <BellRing />
      </span>
      <h2 className={styles.emptyTitle}>No alerts yet</h2>
      <p className={styles.emptyText}>
        Campground full for your dates? Set an alert and we&apos;ll email you the moment every night opens up,
        with a link straight to the booking page.
      </p>
      <div className={styles.emptyActions}>
        <button type="button" className={ui.primary} onClick={onAdd}>
          Add an alert
        </button>
        <Link href="/trail-list" className={ui.secondary}>
          Explore overnight trails
        </Link>
      </div>
    </div>
  );
}

function AlertsContent() {
  const [alerts, setAlerts] = useState<CampgroundAlert[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const [editing, setEditing] = useState<CampgroundAlert | null>(null);
  const [adding, setAdding] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const isHidden = useHidden();
  const today = localToday(now);

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

  // Keeps "checked 12 min ago" current.
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const replace = (updated: CampgroundAlert) =>
    setAlerts((current) => {
      const list = current ?? [];
      return list.some((a) => a.id === updated.id)
        ? list.map((a) => (a.id === updated.id ? updated : a))
        : [updated, ...list];
    });

  // A cancel waiting on its Undo toast shows as cancelled straight away.
  const groups = useMemo(() => {
    const shown = (alerts ?? [])
      .filter((a) => !isHidden(removeKey(a.id)))
      .map((a) => (isHidden(cancelKey(a.id)) && a.status !== "cancelled" ? { ...a, status: "cancelled" as const } : a));
    return groupAlerts(shown, today);
  }, [alerts, isHidden, today]);

  const check = async (alert: CampgroundAlert) => {
    setCheckingId(alert.id);
    try {
      const updated = await alertsApi.check(alert.id);
      replace(updated);
      setNow(new Date());
      if (updated.status === "notified") {
        toast.success("A site opened up! We've emailed you the booking link");
      } else if (updated.last_summary === "available") {
        // Open, but the email didn't go: the poller will try again.
        toast.info(
          "Every night is open right now. Book soon",
          updated.booking_url ? { link: { label: "Book", href: updated.booking_url } } : undefined,
        );
      } else {
        const result = updated.last_summary ? SUMMARY_LABELS[updated.last_summary] : "No opening yet";
        toast.info(`${result}. We'll keep watching`);
      }
    } catch (error) {
      const problem = formProblem(error);
      if (problem) toast.error(problem);
      else toast.failure("check availability", error, () => void check(alert));
    } finally {
      setCheckingId(null);
    }
  };

  const cancel = (alert: CampgroundAlert) =>
    removeWithUndo({
      key: cancelKey(alert.id),
      message: "Alert cancelled",
      what: "cancel the alert",
      commit: async () => replace(await alertsApi.cancel(alert.id)),
    });

  const remove = (alert: CampgroundAlert) =>
    removeWithUndo({
      key: removeKey(alert.id),
      message: "Alert removed",
      what: "remove the alert",
      commit: () => alertsApi.remove(alert.id),
      onCommitted: () => setAlerts((current) => (current ?? []).filter((a) => a.id !== alert.id)),
    });

  const rearm = async (alert: CampgroundAlert) => {
    setBusyId(alert.id);
    try {
      replace(await alertsApi.rearm(alert.id));
      toast.success("Alert turned back on");
    } catch (error) {
      const problem = formProblem(error);
      if (problem) toast.error(problem);
      else toast.failure("turn the alert back on", error, () => void rearm(alert));
    } finally {
      setBusyId(null);
    }
  };

  const counts = groups.map((g) => `${g.alerts.length} ${g.title.toLowerCase()}`).join(" · ");

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
    body = (
      <div className={styles.skeletons} aria-label="Loading">
        <div className={`${ui.skeleton} ${styles.skeleton}`} />
        <div className={`${ui.skeleton} ${styles.skeleton}`} />
      </div>
    );
  } else if (groups.length === 0) {
    body = <EmptyState onAdd={() => setAdding(true)} />;
  } else {
    body = groups.map((group) => (
      <section key={group.key} className={styles.section} aria-labelledby={`alerts-${group.key}`}>
        <div className={styles.sectionHead}>
          <h2 id={`alerts-${group.key}`} className={styles.sectionTitle}>
            {group.title} <span className={styles.count}>{group.alerts.length}</span>
          </h2>
          <p className={styles.sectionHint}>{SECTION_HINTS[group.key]}</p>
        </div>
        <ul className={styles.grid}>
          {group.alerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              group={group.key}
              now={now}
              checking={checkingId === alert.id}
              busy={busyId === alert.id}
              onCheck={() => void check(alert)}
              onEdit={() => setEditing(alert)}
              onCancel={() => cancel(alert)}
              onRearm={() => void rearm(alert)}
              onRemove={() => remove(alert)}
            />
          ))}
        </ul>
      </section>
    ));
  }

  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <header className={styles.header}>
          <div className={styles.headerText}>
            <p className={styles.eyebrow}>Campground alerts</p>
            <h1 className={styles.title}>Get the site when it opens up</h1>
            <p className={styles.lead}>
              Full campground? We watch Parks Canada for you and email once, the moment every night of your
              stay is free. {CADENCE}. Trekly doesn&apos;t book for you, so the email links straight to the
              booking page.
            </p>
            {alerts !== null && groups.length > 0 && <p className={styles.counts}>{counts}</p>}
          </div>
          <button type="button" className={`${ui.primary} ${styles.addButton}`} onClick={() => setAdding(true)}>
            <Plus aria-hidden="true" className={styles.addIcon} />
            Add an alert
          </button>
        </header>

        {body}
      </div>

      {editing && (
        <EditStayDialog
          alert={editing}
          today={today}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            reveal(cancelKey(saved.id));
            replace(saved);
            setEditing(null);
          }}
        />
      )}
      {adding && <NewAlertDialog today={today} onCreated={replace} onClose={() => setAdding(false)} />}
    </main>
  );
}

export default function AlertsPage() {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <RequireAuth fallback={<main className={styles.page} aria-busy="true" />}>
        <AlertsContent />
      </RequireAuth>
    </Suspense>
  );
}
