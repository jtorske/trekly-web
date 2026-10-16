"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import Dialog from "@/components/Dialog";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import {
  PLAN_STATUS_LABELS,
  groupSizeWarning,
  isCheckedStatus,
  isPastPlan,
  nightsInARow,
  siteLabel,
  type DraftNight,
} from "@/lib/planDraft";
import { plansApi, type PlanNight, type TripPlan } from "@/lib/plansApi";
import { formatDay, formatStay, localToday, withStayDates } from "@/lib/stay";
import { getTrailCampgrounds, type TrailCampground } from "@/lib/trailsApi";
import { formatWeight } from "@/lib/units";
import { useUnits } from "@/lib/useUnits";
import FlatLay from "../gear/FlatLay";
import GearList from "../gear/GearList";
import { CORE_SLOTS, groupItemsBySlot, missingTripGear, slotForItem } from "../gear/slots";
import AlertDialog from "../trails/AlertDialog";
import PlanDialog from "./PlanDialog";
import styles from "./page.module.css";

const CHECKED_AT = new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const CHECKED_TIME = new Intl.DateTimeFormat("en-CA", { hour: "numeric", minute: "2-digit" });

/** "checked 2:41 p.m." today, otherwise "checked Oct 14, 2:41 p.m.". */
function checkedLabel(iso: string, today: string): string {
  const at = new Date(iso);
  const sameDay = localToday(at) === today;
  return `checked ${(sameDay ? CHECKED_TIME : CHECKED_AT).format(at)}`;
}

function NightCard({
  night,
  plan,
  today,
  past,
  pending,
  onToggleBooked,
  onAlert,
}: {
  night: PlanNight;
  plan: TripPlan;
  today: string;
  past: boolean;
  pending: boolean;
  onToggleBooked: (night: PlanNight) => void;
  onAlert: (night: PlanNight) => void;
}) {
  const site = night.site;
  const warning = groupSizeWarning(plan.party_size, site?.max_group_size);
  const upcoming = night.date >= today;
  let where;
  if (site) {
    where = (
      <>
        <h3 className={styles.nightPlace}>
          {siteLabel(site)}
          {site.site_code && !site.stop_name && site.site_code !== site.name && (
            <span className={styles.code}>{site.site_code}</span>
          )}
        </h3>
        {site.park && <p className={styles.nightMeta}>{site.park}</p>}
      </>
    );
  } else {
    where = (
      <h3 className={`${styles.nightPlace} ${styles.muted}`}>
        {night.choice === "outside" ? "Outside Parks Canada" : "Not decided"}
      </h3>
    );
  }

  return (
    <li className={styles.night} data-status={night.status ?? "none"}>
      <span className={styles.dot} aria-hidden="true" />
      <div className={styles.nightHead}>
        <span className={styles.nightNumber}>Night {night.night_index + 1}</span>
        <span className={styles.nightDate}>{formatDay(night.date)}</span>
      </div>
      <div className={styles.nightBody}>
        <div className={styles.nightTitleRow}>
          <div>{where}</div>
          {night.status && (
            <span className={styles.pill} data-status={night.status}>
              {PLAN_STATUS_LABELS[night.status]}
              {isCheckedStatus(night.status) && night.last_checked_at && (
                <span className={styles.checkedAt}> · {checkedLabel(night.last_checked_at, today)}</span>
              )}
            </span>
          )}
        </div>
        {night.status === "booked" && isCheckedStatus(night.last_status as PlanNight["status"]) && night.last_checked_at && (
          <p className={styles.nightMeta}>
            Last check: {PLAN_STATUS_LABELS[night.last_status as keyof typeof PLAN_STATUS_LABELS]},{" "}
            {checkedLabel(night.last_checked_at, today)}
          </p>
        )}
        {warning && <p className={styles.warning}>{warning}</p>}
        {site?.retired && <p className={styles.warning}>Parks Canada no longer lists this campground.</p>}
        <div className={styles.nightActions}>
          {night.choice !== "undecided" && (
            <label className={styles.bookedToggle}>
              <input
                type="checkbox"
                checked={night.booked_by_me}
                disabled={pending}
                onChange={() => onToggleBooked(night)}
              />
              Booked by me
            </label>
          )}
          {site?.checkable && !night.booked_by_me && upcoming && !past && (
            night.alert_id ? (
              <Link href="/alerts" className={styles.action}>
                View alert
              </Link>
            ) : (
              <button type="button" className={styles.action} onClick={() => onAlert(night)}>
                Alert me
              </button>
            )
          )}
          {site?.book_url && !site.retired && (
            <a
              href={upcoming ? withStayDates(site.book_url, night.date, nightsInARow(plan.itinerary, night.night_index)) : site.book_url}
              className={styles.action}
              target="_blank"
              rel="noopener noreferrer"
            >
              Book <span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
      </div>
    </li>
  );
}

function GearPanel({ plan, onEdit }: { plan: TripPlan; onEdit: () => void }) {
  const [units] = useUnits();
  const setup = plan.setup;
  if (!setup) {
    return (
      <div className={styles.emptyGear}>
        <p>No gear setup on this plan yet.</p>
        <div className={styles.inlineActions}>
          <button type="button" className={ui.secondary} onClick={onEdit}>
            Choose a setup
          </button>
          <Link href="/gear" className={ui.ghost}>
            Build one in Gear
          </Link>
        </div>
      </div>
    );
  }
  const warnings = missingTripGear(setup.items);
  const others = setup.items.filter((item) => !slotForItem(item).core);
  return (
    <>
      <div className={styles.gearHead}>
        <Link href={`/gear?setup=${encodeURIComponent(setup.id)}`} className={styles.setupName}>
          {setup.name}
        </Link>
        <p className={styles.gearTotals}>
          <strong>{formatWeight(setup.known_weight_g, units)}</strong> known weight
          {setup.items_missing_weight > 0 &&
            ` · ${setup.items_missing_weight} ${setup.items_missing_weight === 1 ? "item has" : "items have"} no weight`}
        </p>
      </div>
      {warnings.length > 0 && (
        <ul className={styles.gearWarnings} aria-label="Missing core gear">
          {warnings.map((w) => (
            <li key={w.key} className={styles.gearWarning} data-level={w.level}>
              {w.level === "warning" ? "⚠ " : ""}
              {w.message}
            </li>
          ))}
        </ul>
      )}
      <div className={styles.mat}>
        <FlatLay
          slots={CORE_SLOTS}
          bySlot={groupItemsBySlot(setup.items)}
          showEmptySlots={false}
          units={units}
          canEdit={false}
          addDisabled
          snapId={null}
          emptyMessage={setup.items.length === 0 ? "This setup is empty." : null}
          onAdd={() => undefined}
          onOpen={() => undefined}
        />
      </div>
      {others.length > 0 && (
        <>
          <h3 className={styles.subTitle}>More gear</h3>
          <GearList items={others} units={units} compact />
        </>
      )}
    </>
  );
}

function PlanView({ id }: { id: string }) {
  const router = useRouter();
  const [today] = useState(() => localToday());
  const [state, setState] = useState<{ id: string; plan: TripPlan | null; error: string | null } | null>(null);
  const [campgrounds, setCampgrounds] = useState<TrailCampground[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingNight, setPendingNight] = useState<number | null>(null);
  const [checking, setChecking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [alertNight, setAlertNight] = useState<PlanNight | null>(null);
  const [token, setToken] = useState(0);
  const reload = useCallback(() => setToken((t) => t + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    plansApi
      .get(id, controller.signal)
      .then((plan) => setState({ id, plan, error: null }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        const message = error instanceof ApiError && error.status === 404 ? null : error instanceof Error ? error.message : "Couldn't load this plan.";
        setState({ id, plan: null, error: message });
      });
    return () => controller.abort();
  }, [id, token]);

  const plan = state?.id === id ? state.plan : null;
  const trailId = plan?.trail.id;
  useEffect(() => {
    if (!trailId) return;
    const controller = new AbortController();
    getTrailCampgrounds(trailId, controller.signal)
      .then((data) => setCampgrounds(data.campgrounds))
      .catch(() => undefined);
    return () => controller.abort();
  }, [trailId]);

  if (!state || state.id !== id) return <PlanSkeleton />;
  if (!plan) {
    return (
      <div className={styles.status}>
        {state.error ? (
          <p className={ui.error} role="alert">
            {state.error}{" "}
            <button type="button" className={ui.ghost} onClick={reload}>
              Try again
            </button>
          </p>
        ) : (
          <>
            <h1 className={styles.notFoundTitle}>Plan not found</h1>
            <p>It may have been deleted.</p>
            <Link href="/profile?tab=trips" className={styles.inlineLink}>
              Your trip plans
            </Link>
          </>
        )}
      </div>
    );
  }

  const past = isPastPlan(plan, today);
  const canCheck = !past && plan.itinerary.some((n) => n.site?.checkable && n.date >= today);
  const booked = plan.booked_nights;

  const toggleBooked = async (night: PlanNight) => {
    setPendingNight(night.night_index);
    setActionError(null);
    try {
      setState({ id, plan: await plansApi.setBooked(plan.id, night.night_index, !night.booked_by_me), error: null });
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "That didn't save. Try again.");
    } finally {
      setPendingNight(null);
    }
  };

  const check = async () => {
    setChecking(true);
    setActionError(null);
    try {
      setState({ id, plan: await plansApi.check(plan.id), error: null });
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "We couldn't check availability right now.");
    } finally {
      setChecking(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await plansApi.remove(plan.id);
      router.push("/profile?tab=trips");
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "That plan didn't delete. Try again.");
      setDeleting(false);
      setBusy(false);
    }
  };

  const draftItinerary: DraftNight[] = plan.itinerary.map((n) => ({ choice: n.choice, siteId: n.site?.id ?? null }));
  const actions = (
    <>
      <button type="button" className={ui.secondary} onClick={() => setEditing(true)} disabled={!campgrounds}>
        Edit
      </button>
      <button type="button" className={ui.ghost} onClick={() => setDeleting(true)}>
        Delete
      </button>
    </>
  );

  return (
    <article>
      <Link href={`/trails?id=${encodeURIComponent(plan.trail.id)}`} className={styles.backLink}>
        ← {plan.trail.name}
      </Link>
      <header className={styles.header}>
        <div className={styles.headerText}>
          <p className={styles.region}>{plan.trail.region}</p>
          <h1 className={styles.title}>{plan.title ?? plan.trail.name}</h1>
          <p className={styles.meta}>
            {formatStay(plan.start_date, plan.nights)} · party of {plan.party_size}
            {past && <span className={`${ui.badge} ${styles.pastBadge}`}>Past trip</span>}
          </p>
          <p className={styles.meta}>
            {booked} of {plan.nights} {plan.nights === 1 ? "night" : "nights"} booked
          </p>
        </div>
        <div className={styles.headerActions}>{actions}</div>
        <details className={styles.overflow}>
          <summary aria-label="Plan actions">⋯</summary>
          <div className={styles.overflowMenu}>{actions}</div>
        </details>
      </header>

      {actionError && (
        <p className={ui.error} role="alert">
          {actionError}
        </p>
      )}

      <section className={styles.section} aria-labelledby="itinerary-title">
        <div className={styles.sectionHead}>
          <h2 id="itinerary-title" className={styles.sectionTitle}>
            Itinerary
          </h2>
          {canCheck && (
            <button type="button" className={ui.secondary} onClick={check} disabled={checking}>
              {checking ? "Checking…" : "Check availability"}
            </button>
          )}
        </div>
        {plan.permits.length > 0 && (
          <p className={styles.permit}>
            Also needs{" "}
            {plan.permits.map((permit, i) => (
              <span key={permit.name}>
                {i > 0 && ", "}
                {permit.book_url ? (
                  <a href={past ? permit.book_url : withStayDates(permit.book_url, plan.start_date, plan.nights)} target="_blank" rel="noopener noreferrer">
                    {permit.name} <span aria-hidden="true">↗</span>
                  </a>
                ) : (
                  permit.name
                )}
              </span>
            ))}
          </p>
        )}
        <ol className={styles.timeline}>
          {plan.itinerary.map((night) => (
            <NightCard
              key={night.night_index}
              night={night}
              plan={plan}
              today={today}
              past={past}
              pending={pendingNight === night.night_index}
              onToggleBooked={toggleBooked}
              onAlert={setAlertNight}
            />
          ))}
        </ol>
        <p className={styles.footnote}>
          Trekly doesn&apos;t book for you. Mark nights as booked once you&apos;ve reserved them, and check again
          before you go: availability changes.
        </p>
      </section>

      <section className={styles.section} aria-labelledby="gear-title">
        <h2 id="gear-title" className={styles.sectionTitle}>
          Gear
        </h2>
        <GearPanel plan={plan} onEdit={() => setEditing(true)} />
      </section>

      {plan.notes && (
        <section className={styles.section} aria-labelledby="notes-title">
          <h2 id="notes-title" className={styles.sectionTitle}>
            Notes
          </h2>
          <p className={styles.notes}>{plan.notes}</p>
        </section>
      )}

      {editing && campgrounds && (
        <PlanDialog
          trailId={plan.trail.id}
          trailName={plan.trail.name}
          campgrounds={campgrounds}
          initial={{
            title: plan.title ?? "",
            notes: plan.notes ?? "",
            setupId: plan.setup_id,
            stay: { start: plan.start_date, nights: plan.nights, party: plan.party_size },
            itinerary: draftItinerary,
          }}
          today={today}
          plan={plan}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setState({ id, plan: saved, error: null });
            setEditing(false);
          }}
        />
      )}

      {deleting && (
        <Dialog
          title="Delete this trip plan?"
          onClose={() => setDeleting(false)}
          busy={busy}
          size="sm"
          footer={
            <>
              <button type="button" className={ui.ghost} onClick={() => setDeleting(false)} disabled={busy}>
                Cancel
              </button>
              <button type="button" className={ui.danger} onClick={remove} disabled={busy} data-autofocus>
                {busy ? "Deleting…" : "Delete plan"}
              </button>
            </>
          }
        >
          <p>
            {plan.title ?? plan.trail.name}, {formatStay(plan.start_date, plan.nights)}. Anything you&apos;ve booked
            on Parks Canada stays booked.
          </p>
        </Dialog>
      )}

      {alertNight?.site && (
        <AlertDialog
          trailId={plan.trail.id}
          siteId={alertNight.site.id}
          campground={siteLabel(alertNight.site)}
          stay={{ start: alertNight.date, nights: 1, party: plan.party_size }}
          returnTo={`/plans?id=${encodeURIComponent(plan.id)}`}
          onClose={() => {
            setAlertNight(null);
            reload();
          }}
        />
      )}
    </article>
  );
}

function PlanSkeleton() {
  return (
    <div className={styles.skeleton} aria-busy="true" aria-label="Loading plan">
      <div className={ui.skeleton} style={{ height: "2.5rem", width: "60%" }} />
      <div className={ui.skeleton} style={{ height: "1rem", width: "40%" }} />
      <div className={ui.skeleton} style={{ height: "14rem" }} />
    </div>
  );
}

function PlanContent() {
  const id = useSearchParams().get("id");
  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <RequireAuth fallback={<PlanSkeleton />}>
          {id ? (
            <PlanView id={id} />
          ) : (
            <div className={styles.status}>
              <h1 className={styles.notFoundTitle}>No plan picked</h1>
              <Link href="/profile?tab=trips" className={styles.inlineLink}>
                Your trip plans
              </Link>
            </div>
          )}
        </RequireAuth>
      </div>
    </main>
  );
}

export default function PlanPage() {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <PlanContent />
    </Suspense>
  );
}
