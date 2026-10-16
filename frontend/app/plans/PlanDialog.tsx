"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/api";
import { MAX_NIGHTS, MAX_PARTY, type Stay } from "@/lib/availabilityApi";
import { nextQuery } from "@/lib/authLogic";
import {
  OUTSIDE,
  UNDECIDED,
  bookedNightsLost,
  describeNight,
  groupSizeWarning,
  listPhrase,
  resizeItinerary,
  siteLabel,
  sleepableSites,
  type DraftNight,
} from "@/lib/planDraft";
import { plansApi, type PlanInput, type TripPlan } from "@/lib/plansApi";
import { addDays, formatDay, formatStay } from "@/lib/stay";
import type { TrailCampground } from "@/lib/trailsApi";
import { useSetups } from "../gear/useSetups";
import { groupStops } from "../trails/campgrounds";
import styles from "./PlanDialog.module.css";

export interface PlanDraft {
  title: string;
  stay: Stay;
  itinerary: DraftNight[];
  setupId: string | null;
  notes: string;
}

function encodeNight(night: DraftNight): string {
  return night.choice === "campground" && night.siteId ? `site:${night.siteId}` : night.choice;
}

function decodeNight(value: string): DraftNight {
  if (value.startsWith("site:")) return { choice: "campground", siteId: value.slice(5) };
  return value === "outside" ? OUTSIDE : UNDECIDED;
}

/**
 * "Plan this trip": dates, party, one campground per night (this trail's,
 * in route order), a gear setup and notes. Guests can fill it in and are
 * asked to sign in only when they save; `guestReturnTo` brings them back with
 * the draft. Editing an existing plan asks before unmarking booked nights.
 */
export default function PlanDialog({
  trailId,
  trailName,
  campgrounds,
  initial,
  today,
  plan,
  guestReturnTo,
  onBeforeSignIn,
  onClose,
  onSaved,
}: {
  trailId: string;
  trailName: string;
  campgrounds: TrailCampground[];
  initial: PlanDraft;
  today: string;
  /** Set when editing. */
  plan?: TripPlan;
  guestReturnTo?: (draft: PlanDraft) => string;
  /** Lets the opener keep what the URL can't carry (title, notes). */
  onBeforeSignIn?: (draft: PlanDraft) => void;
  onClose: () => void;
  /** Called after an edit is saved. New plans open their plan page instead. */
  onSaved?: (plan: TripPlan) => void;
}) {
  const router = useRouter();
  const { status } = useAuth();
  const signedIn = status === "signedIn";
  const setups = useSetups();
  const [draft, setDraft] = useState<PlanDraft>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const sites = useMemo(() => sleepableSites(campgrounds), [campgrounds]);
  const byId = useMemo(() => new Map(sites.map((site) => [site.site_id, site])), [sites]);
  const stops = useMemo(() => groupStops(sites), [sites]);

  const set = (patch: Partial<PlanDraft>) => {
    setConfirming(null);
    setDraft((current) => ({ ...current, ...patch }));
  };
  const setStay = (stay: Partial<Stay>) => {
    const next = { ...draft.stay, ...stay };
    set({ stay: next, itinerary: resizeItinerary(draft.itinerary, next.nights) });
  };
  const setNight = (index: number, night: DraftNight) =>
    set({ itinerary: draft.itinerary.map((n, i) => (i === index ? night : n)) });

  const input = (confirm: boolean): PlanInput => ({
    title: draft.title.trim() || null,
    start_date: draft.stay.start,
    nights: draft.stay.nights,
    party_size: draft.stay.party,
    setup_id: draft.setupId,
    notes: draft.notes.trim() || null,
    itinerary: draft.itinerary.map((n) => ({ choice: n.choice, site_id: n.choice === "campground" ? n.siteId : null })),
    confirm_drop_booked: confirm,
  });

  const save = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!signedIn) return;
    if (plan && !confirming) {
      const lost = bookedNightsLost(plan, draft.stay.start, draft.itinerary);
      if (lost.length > 0) {
        setConfirming(
          `This will unmark ${listPhrase(lost.map((n) => describeNight(n, formatDay)))} as booked.`,
        );
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      if (plan) {
        const saved = await plansApi.update(plan.id, input(Boolean(confirming)));
        setBusy(false);
        onSaved?.(saved);
      } else {
        const saved = await plansApi.create(trailId, input(false));
        // Stay busy until the plan page opens, so a slow navigation can't
        // invite a second save.
        router.push(`/plans?id=${encodeURIComponent(saved.id)}`);
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "That plan didn't save. Try again.");
      setConfirming(null);
      setBusy(false);
    }
  };

  // A retired campground already on this plan stays selectable where it is.
  const retiredOption = (night: DraftNight) =>
    night.choice === "campground" && night.siteId && !byId.get(night.siteId)
      ? plan?.itinerary.find((n) => n.site?.id === night.siteId)?.site ?? null
      : null;

  let footer;
  if (!signedIn) {
    footer = (
      <>
        <button type="button" className={ui.ghost} onClick={onClose}>
          Not now
        </button>
        <Link
          href={`/login${nextQuery(guestReturnTo ? guestReturnTo(draft) : `/trails?id=${encodeURIComponent(trailId)}`)}`}
          className={ui.primary}
          onClick={() => onBeforeSignIn?.(draft)}
        >
          Sign in to save plan
        </Link>
      </>
    );
  } else if (confirming) {
    footer = (
      <>
        <button type="button" className={ui.ghost} onClick={() => setConfirming(null)} disabled={busy}>
          Go back
        </button>
        <button type="button" className={ui.danger} onClick={() => save()} disabled={busy} data-autofocus>
          {busy ? "Saving…" : "Unmark and save"}
        </button>
      </>
    );
  } else {
    footer = (
      <>
        <button type="button" className={ui.ghost} onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" form="plan-form" className={ui.primary} disabled={busy}>
          {busy ? "Saving…" : plan ? "Save changes" : "Save plan"}
        </button>
      </>
    );
  }

  return (
    <Dialog
      title={plan ? "Edit trip plan" : "Plan this trip"}
      subtitle={
        <>
          <strong>{trailName}</strong> · {formatStay(draft.stay.start, draft.stay.nights)} · party of {draft.stay.party}
        </>
      }
      onClose={onClose}
      busy={busy}
      size="lg"
      sheet
      footer={footer}
    >
      <form id="plan-form" className={styles.form} onSubmit={save} noValidate>
        <div className={styles.stay}>
          <label className={ui.field}>
            <span className={ui.label}>First night</span>
            <input
              type="date"
              className={ui.input}
              value={draft.stay.start}
              min={plan ? undefined : today}
              required
              onChange={(event) => event.target.value && setStay({ start: event.target.value })}
            />
          </label>
          <label className={ui.field}>
            <span className={ui.label}>Nights</span>
            <select
              className={ui.input}
              value={draft.stay.nights}
              onChange={(event) => setStay({ nights: Number(event.target.value) })}
            >
              {Array.from({ length: MAX_NIGHTS }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className={ui.field}>
            <span className={ui.label}>People</span>
            <select
              className={ui.input}
              value={draft.stay.party}
              onChange={(event) => setStay({ party: Number(event.target.value) })}
            >
              {Array.from({ length: MAX_PARTY }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className={styles.nights}>
          <legend className={ui.label}>Where you&apos;ll sleep</legend>
          <ol className={styles.nightList}>
            {draft.itinerary.map((night, index) => {
              const retired = retiredOption(night);
              const chosen = night.siteId ? byId.get(night.siteId) : undefined;
              const warning = groupSizeWarning(draft.stay.party, chosen?.max_group_size ?? retired?.max_group_size);
              const date = addDays(draft.stay.start, index);
              return (
                <li key={index} className={styles.nightRow}>
                  <label className={styles.nightLabel} htmlFor={`plan-night-${index}`}>
                    <span className={styles.nightNumber}>Night {index + 1}</span>
                    <span className={styles.nightDate}>{formatDay(date)}</span>
                  </label>
                  <div className={styles.nightField}>
                    <select
                      id={`plan-night-${index}`}
                      className={ui.input}
                      value={encodeNight(night)}
                      onChange={(event) => setNight(index, decodeNight(event.target.value))}
                      aria-describedby={warning ? `plan-night-${index}-warning` : undefined}
                    >
                      <option value="undecided">Not decided</option>
                      {retired && <option value={`site:${retired.id}`}>{siteLabel(retired)} (no longer listed)</option>}
                      {stops.map((stop) => {
                        const open = stop.sites.filter((site) => !site.retired);
                        if (open.length === 0) return null;
                        if (open.length === 1 && stop.sites.length === 1) {
                          const site = open[0];
                          return (
                            <option key={site.site_id} value={`site:${site.site_id}`}>
                              {site.site_code && site.site_code !== site.name ? `${site.name} (${site.site_code})` : site.name}
                            </option>
                          );
                        }
                        return (
                          <optgroup key={stop.key} label={stop.label}>
                            {open.map((site) => (
                              <option key={site.site_id} value={`site:${site.site_id}`}>
                                {stop.label} {site.site_code ?? site.name}
                              </option>
                            ))}
                          </optgroup>
                        );
                      })}
                      <option value="outside">Outside Parks Canada</option>
                    </select>
                    {warning && (
                      <p id={`plan-night-${index}-warning`} className={styles.warning}>
                        {warning}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </fieldset>

        <label className={ui.field}>
          <span className={ui.label}>Gear setup</span>
          {signedIn ? (
            setups.setups.length > 0 || draft.setupId ? (
              <select
                className={ui.input}
                value={draft.setupId ?? ""}
                onChange={(event) => set({ setupId: event.target.value || null })}
              >
                <option value="">No setup</option>
                {setups.setups.map((setup) => (
                  <option key={setup.id} value={setup.id}>
                    {setup.name}
                  </option>
                ))}
              </select>
            ) : (
              <span className={ui.hint}>
                {setups.loading ? "Loading your setups…" : (
                  <>
                    You don&apos;t have a setup yet.{" "}
                    <Link href="/gear" target="_blank" className={styles.link}>
                      Create one <span aria-hidden="true">↗</span>
                    </Link>
                  </>
                )}
              </span>
            )
          ) : (
            <span className={ui.hint}>Sign in to attach one of your gear setups.</span>
          )}
        </label>

        <label className={ui.field}>
          <span className={ui.label}>Title (optional)</span>
          <input
            className={ui.input}
            value={draft.title}
            maxLength={80}
            placeholder={trailName}
            onChange={(event) => set({ title: event.target.value })}
          />
        </label>

        <label className={ui.field}>
          <span className={ui.label}>Notes (optional)</span>
          <textarea
            className={ui.input}
            rows={3}
            maxLength={2000}
            value={draft.notes}
            onChange={(event) => set({ notes: event.target.value })}
          />
        </label>

        {!signedIn && (
          <p className={ui.hint}>Planning is free. You&apos;ll sign in to save it to your account.</p>
        )}
        {confirming && (
          <p className={ui.notice} role="alert">
            {`${confirming} Trekly doesn't cancel anything on Parks Canada.`}
          </p>
        )}
        {error && (
          <p className={ui.error} role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
