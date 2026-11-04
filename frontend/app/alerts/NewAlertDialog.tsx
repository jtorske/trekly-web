"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import { choosePickerTrail, pickerOrder, pickerSearch, unwatchableReason } from "@/lib/alertWatch";
import type { CampgroundAlert, Stay } from "@/lib/availabilityApi";
import { partyLimitProblem } from "@/lib/alertRules";
import { defaultStay } from "@/lib/stay";
import { getTrailCampgrounds, searchTrails, type TrailCampground, type TrailPickItem } from "@/lib/trailsApi";
import AlertDialog from "../trails/AlertDialog";
import StayFields from "./StayFields";
import styles from "./AlertDialogs.module.css";

/**
 * One search result. A trail alerts can't watch stays in the list (so a
 * search for it explains why) but is greyed out and aria-disabled: click,
 * Enter and Space only point at its reason, never select it.
 */
function TrailResult({
  trail,
  explained,
  onChoose,
}: {
  trail: TrailPickItem;
  explained: boolean;
  onChoose: (trail: TrailPickItem) => void;
}) {
  const reasonId = useId();
  const disabled = !trail.has_watchable_campgrounds;
  return (
    <li>
      <button
        type="button"
        className={styles.result}
        aria-disabled={disabled || undefined}
        aria-describedby={disabled ? reasonId : undefined}
        data-explained={explained || undefined}
        onClick={() => onChoose(trail)}
      >
        <span className={styles.resultName}>{trail.name}</span>
        <span className={styles.resultMeta}>{trail.park_name ?? trail.region}</span>
        {disabled && (
          <span id={reasonId} className={styles.resultReason}>
            {unwatchableReason(trail)}
          </span>
        )}
      </button>
    </li>
  );
}

function TrailSearch({ onPick }: { onPick: (trail: TrailPickItem) => void }) {
  const [query, setQuery] = useState("");
  const [showUnwatchable, setShowUnwatchable] = useState(false);
  const [results, setResults] = useState<TrailPickItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [explained, setExplained] = useState<{ id: string; message: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchTrails(query.trim(), controller.signal, {
        trip: "overnight",
        // Every match, so the greyed-out trails still fit below the watchable
        // ones (the list scrolls); overnight trails are a small set.
        limit: 60,
        ...pickerSearch(query, showUnwatchable),
      })
        .then((found) => {
          setResults(pickerOrder(found));
          setFailed(false);
          setExplained(null);
        })
        .catch((error: unknown) => {
          if ((error as { name?: string }).name !== "AbortError") setFailed(true);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, showUnwatchable]);

  const choose = (trail: TrailPickItem) => {
    const choice = choosePickerTrail(trail);
    if (choice.kind === "pick") onPick(choice.trail);
    else setExplained({ id: trail.id, message: `${trail.name} can't have alerts. ${choice.reason}` });
  };

  return (
    <>
      <label className={ui.field}>
        <span className={ui.label}>Overnight trail</span>
        <input
          className={ui.input}
          type="search"
          value={query}
          placeholder="Search by trail or park"
          onChange={(event) => setQuery(event.target.value)}
          data-autofocus
        />
      </label>
      <label className={styles.showToggle}>
        <input
          type="checkbox"
          checked={showUnwatchable}
          onChange={(event) => setShowUnwatchable(event.target.checked)}
        />
        Show trails without alerts
      </label>
      {failed ? (
        <p className={ui.error} role="alert">
          We couldn&apos;t search trails right now. Try again shortly.
        </p>
      ) : results === null ? (
        <div className={`${ui.skeleton} ${styles.resultsSkeleton}`} aria-label="Loading" />
      ) : results.length === 0 ? (
        <p className={ui.hint}>
          {query.trim()
            ? <>No overnight trails match &ldquo;{query.trim()}&rdquo;.</>
            : "No overnight trails can have alerts yet."}
        </p>
      ) : (
        <ul className={styles.results} aria-label="Trails">
          {results.map((trail) => (
            <TrailResult key={trail.id} trail={trail} explained={explained?.id === trail.id} onChoose={choose} />
          ))}
        </ul>
      )}
      <p className={ui.srOnly} role="status">
        {explained?.message ?? ""}
      </p>
    </>
  );
}

/**
 * "Add an alert" from the alerts page: pick an overnight trail, one of its
 * campgrounds and a stay, then confirm in the same dialog the trail page uses.
 */
export default function NewAlertDialog({
  today,
  onCreated,
  onClose,
}: {
  today: string;
  onCreated: (alert: CampgroundAlert) => void;
  onClose: () => void;
}) {
  const [trail, setTrail] = useState<TrailPickItem | null>(null);
  const [campgrounds, setCampgrounds] = useState<TrailCampground[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [stay, setStay] = useState<Stay>(() => defaultStay(today, null));
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!trail) return;
    const controller = new AbortController();
    getTrailCampgrounds(trail.id, controller.signal)
      .then((found) => {
        const options = found.campgrounds.filter((c) => c.watchable);
        setCampgrounds(options);
        setSiteId(options.length === 1 ? options[0].site_id : null);
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setLoadFailed(true);
      });
    return () => controller.abort();
  }, [trail]);

  const pickTrail = (picked: TrailPickItem) => {
    setCampgrounds(null);
    setLoadFailed(false);
    setSiteId(null);
    setStay(defaultStay(today, picked.typical_duration_nights));
    setTrail(picked);
  };

  const site = campgrounds?.find((c) => c.site_id === siteId) ?? null;
  const tooMany = site ? partyLimitProblem(site, stay.party) : null;

  if (confirming && trail && site) {
    return (
      <AlertDialog
        trailId={trail.id}
        siteId={site.site_id}
        campground={site.name}
        maxGroupSize={site.max_group_size}
        stay={stay}
        returnTo="/alerts"
        onCreated={onCreated}
        onClose={onClose}
      />
    );
  }

  const next = (event: FormEvent) => {
    event.preventDefault();
    if (site && !tooMany) setConfirming(true);
  };

  let body;
  if (!trail) {
    body = <TrailSearch onPick={pickTrail} />;
  } else {
    body = (
      <form id="new-alert" onSubmit={next}>
        <div className={styles.picked}>
          <span>
            <span className={styles.resultName}>{trail.name}</span>
            <span className={styles.resultMeta}>{trail.park_name ?? trail.region}</span>
          </span>
          <button type="button" className={ui.ghost} onClick={() => setTrail(null)}>
            Change
          </button>
        </div>
        {loadFailed ? (
          <p className={ui.error} role="alert">
            We couldn&apos;t load this trail&apos;s campgrounds. Try again shortly.
          </p>
        ) : campgrounds === null ? (
          <div className={`${ui.skeleton} ${styles.resultsSkeleton}`} aria-label="Loading" />
        ) : campgrounds.length === 0 ? (
          // Only reachable if the trail's campgrounds changed since the search.
          <p className={ui.hint}>{unwatchableReason(trail)}</p>
        ) : (
          <>
            <fieldset className={styles.campgrounds}>
              <legend className={ui.label}>Campground</legend>
              {campgrounds.map((c) => (
                <label key={c.site_id} className={styles.campground}>
                  <input
                    type="radio"
                    name="campground"
                    value={c.site_id}
                    checked={siteId === c.site_id}
                    onChange={() => setSiteId(c.site_id)}
                  />
                  <span>
                    {c.name}
                    {c.site_code && c.site_code !== c.name && <span className={styles.code}> {c.site_code}</span>}
                  </span>
                </label>
              ))}
            </fieldset>
            <StayFields stay={stay} today={today} onChange={setStay} />
            {tooMany && (
              <p className={ui.error} role="alert">
                {tooMany}
              </p>
            )}
          </>
        )}
      </form>
    );
  }

  return (
    <Dialog
      title="Add an alert"
      subtitle={trail ? "Pick a campground and your dates." : "Find the overnight trail you want to camp on."}
      size="md"
      onClose={onClose}
      footer={
        <>
          <button type="button" className={ui.ghost} onClick={onClose}>
            Cancel
          </button>
          {trail && (
            <button type="submit" form="new-alert" className={ui.primary} disabled={!site || Boolean(tooMany)}>
              Continue
            </button>
          )}
        </>
      }
    >
      {body}
    </Dialog>
  );
}
