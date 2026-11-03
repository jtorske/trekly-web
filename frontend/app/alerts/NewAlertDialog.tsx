"use client";

import { useEffect, useState, type FormEvent } from "react";
import Dialog from "@/components/Dialog";
import ui from "@/components/ui.module.css";
import type { CampgroundAlert, Stay } from "@/lib/availabilityApi";
import { defaultStay } from "@/lib/stay";
import {
  getTrailCampgrounds,
  searchTrails,
  type TrailCampground,
  type TrailListItem,
} from "@/lib/trailsApi";
import AlertDialog from "../trails/AlertDialog";
import StayFields from "./StayFields";
import styles from "./AlertDialogs.module.css";

/** Parks Canada campgrounds still listed: the ones an alert can watch. */
function watchable(campgrounds: TrailCampground[]): TrailCampground[] {
  return campgrounds.filter((c) => c.provider === "parks_canada" && !c.retired && c.kind !== "trail_permit");
}

function TrailSearch({ onPick }: { onPick: (trail: TrailListItem) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TrailListItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchTrails(query.trim(), controller.signal, { trip: "overnight", limit: 8 })
        .then((found) => {
          setResults(found);
          setFailed(false);
        })
        .catch((error: unknown) => {
          if ((error as { name?: string }).name !== "AbortError") setFailed(true);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

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
      {failed ? (
        <p className={ui.error} role="alert">
          We couldn&apos;t search trails right now. Try again shortly.
        </p>
      ) : results === null ? (
        <div className={`${ui.skeleton} ${styles.resultsSkeleton}`} aria-label="Loading" />
      ) : results.length === 0 ? (
        <p className={ui.hint}>No overnight trails match &ldquo;{query.trim()}&rdquo;.</p>
      ) : (
        <ul className={styles.results} aria-label="Trails">
          {results.map((trail) => (
            <li key={trail.id}>
              <button type="button" className={styles.result} onClick={() => onPick(trail)}>
                <span className={styles.resultName}>{trail.name}</span>
                <span className={styles.resultMeta}>{trail.park_name ?? trail.region}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
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
  const [trail, setTrail] = useState<TrailListItem | null>(null);
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
        const options = watchable(found.campgrounds);
        setCampgrounds(options);
        setSiteId(options.length === 1 ? options[0].site_id : null);
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setLoadFailed(true);
      });
    return () => controller.abort();
  }, [trail]);

  const pickTrail = (picked: TrailListItem) => {
    setCampgrounds(null);
    setLoadFailed(false);
    setSiteId(null);
    setStay(defaultStay(today, picked.typical_duration_nights));
    setTrail(picked);
  };

  const site = campgrounds?.find((c) => c.site_id === siteId) ?? null;

  if (confirming && trail && site) {
    return (
      <AlertDialog
        trailId={trail.id}
        siteId={site.site_id}
        campground={site.name}
        stay={stay}
        returnTo="/alerts"
        onCreated={onCreated}
        onClose={onClose}
      />
    );
  }

  const next = (event: FormEvent) => {
    event.preventDefault();
    if (site) setConfirming(true);
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
          <p className={ui.hint}>
            None of this trail&apos;s campgrounds can be watched online. Alerts work for Parks Canada
            campgrounds.
          </p>
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
            <button type="submit" form="new-alert" className={ui.primary} disabled={!site}>
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
