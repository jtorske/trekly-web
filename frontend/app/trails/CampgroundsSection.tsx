"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import {
  MAX_NIGHTS,
  MAX_PARTY,
  checkTrailAvailability,
  type CampgroundAvailability,
  type Stay,
  type TrailAvailability,
} from "@/lib/availabilityApi";
import {
  NIGHT_LABELS,
  SUMMARY_LABELS,
  canAlert,
  defaultStay,
  formatDay,
  formatNight,
  localToday,
  sentence,
  stayFromParams,
  stayParams,
} from "@/lib/stay";
import type { TrailBooking, TrailCampground, TrailCampgrounds } from "@/lib/trailsApi";
import AlertDialog from "./AlertDialog";
import { bookingLabel, campgroundView, capacityFacts, kindLabel, type Stop } from "./campgrounds";
import styles from "./CampgroundsSection.module.css";

function BookingNote({ booking }: { booking: TrailBooking }) {
  return (
    <div className={styles.elsewhere}>
      <p className={styles.elsewhereTitle}>
        {booking.url ? (
          <a href={booking.url} target="_blank" rel="noopener noreferrer">
            {bookingLabel(booking)}{" "}<span aria-hidden="true">↗</span>
          </a>
        ) : (
          bookingLabel(booking)
        )}
      </p>
      {booking.note && <p className={styles.elsewhereNote}>{booking.note}</p>}
    </div>
  );
}

function NightStrip({ found }: { found: CampgroundAvailability }) {
  return (
    <ul className={styles.nights} aria-label="Nights">
      {found.nights.map((night) => (
        <li
          key={night.date}
          className={`${styles.night} ${styles[`night_${night.status}`]}`}
          title={`${formatDay(night.date)}: ${NIGHT_LABELS[night.status]}`}
          aria-label={`${formatDay(night.date)}: ${NIGHT_LABELS[night.status]}`}
        >
          {formatNight(night.date)}
        </li>
      ))}
    </ul>
  );
}

function Availability({
  site,
  found,
  label,
  onAlert,
}: {
  site: TrailCampground;
  found: CampgroundAvailability | undefined;
  label?: string;
  onAlert: (site: TrailCampground) => void;
}) {
  if (!found) return null;
  return (
    <div className={styles.availability}>
      {label && <span className={styles.padLabel}>{label}</span>}
      <NightStrip found={found} />
      <span className={`${styles.summary} ${styles[`summary_${found.summary}`]}`}>{SUMMARY_LABELS[found.summary]}</span>
      {canAlert(found.summary) && (
        <button type="button" className={styles.alertButton} onClick={() => onAlert(site)}>
          Alert me
        </button>
      )}
    </div>
  );
}

function StopRow({
  stop,
  index,
  availability,
  onAlert,
}: {
  stop: Stop;
  index: number;
  availability: Map<string, CampgroundAvailability>;
  onAlert: (site: TrailCampground) => void;
}) {
  const first = stop.sites[0];
  const isGroup = stop.sites.length > 1;
  const code = isGroup ? null : first.site_code;
  const facts = isGroup ? [] : capacityFacts(first);
  const notes = [...new Set(stop.sites.map((site) => site.notes).filter(Boolean))];
  const checked = stop.sites.some((site) => availability.has(site.site_id));

  return (
    <li className={`${styles.stop} ${stop.retired ? styles.retired : ""}`}>
      <span className={styles.marker} aria-hidden="true">
        {index + 1}
      </span>
      <div className={styles.body}>
        <div className={styles.titleRow}>
          <h3 className={styles.name}>
            {stop.label}
            {code && code !== stop.label && <span className={styles.code}>{code}</span>}
          </h3>
          <span className={styles.kind}>{kindLabel(first.kind, stop.sites.length)}</span>
        </div>
        <p className={styles.meta}>{[first.park?.name, ...facts].filter(Boolean).join(" · ")}</p>
        {isGroup && !checked && (
          <ul className={styles.pads} aria-label={`Campsites at ${stop.label}`}>
            {stop.sites.map((site) => (
              <li key={site.site_id} className={site.retired ? styles.padRetired : undefined}>
                {site.site_code ?? site.name}
              </li>
            ))}
          </ul>
        )}
        {notes.map((note) => (
          <p key={note} className={styles.note}>
            {note}
          </p>
        ))}
        {stop.sites.map((site) => (
          <Availability
            key={site.site_id}
            site={site}
            found={availability.get(site.site_id)}
            label={isGroup ? (site.site_code ?? site.name) : undefined}
            onAlert={onAlert}
          />
        ))}
        {stop.retired && <p className={styles.retiredNote}>No longer listed by Parks Canada</p>}
      </div>
    </li>
  );
}

function StayForm({
  stay,
  today,
  busy,
  onChange,
  onSubmit,
}: {
  stay: Stay;
  today: string;
  busy: boolean;
  onChange: (stay: Stay) => void;
  onSubmit: () => void;
}) {
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };
  return (
    <form className={styles.stayForm} onSubmit={submit} aria-label="Check availability">
      <label className={`${ui.field} ${styles.startField}`}>
        <span className={ui.label}>First night</span>
        <input
          type="date"
          className={ui.input}
          value={stay.start}
          min={today}
          required
          onChange={(event) => event.target.value && onChange({ ...stay, start: event.target.value })}
        />
      </label>
      <label className={ui.field}>
        <span className={ui.label}>Nights</span>
        <select
          className={ui.input}
          value={stay.nights}
          onChange={(event) => onChange({ ...stay, nights: Number(event.target.value) })}
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
          value={stay.party}
          onChange={(event) => onChange({ ...stay, party: Number(event.target.value) })}
        >
          {Array.from({ length: MAX_PARTY }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className={`${ui.primary} ${styles.checkButton}`} disabled={busy}>
        {busy ? "Checking…" : "Check availability"}
      </button>
    </form>
  );
}

const TIME = new Intl.DateTimeFormat("en-CA", { hour: "numeric", minute: "2-digit" });

function checkedStatus(checkedAt: string | null): string {
  const when = checkedAt ? `, checked at ${TIME.format(new Date(checkedAt))}` : "";
  return `${sentence(`Live from Parks Canada${when}`)} Each date is a night you sleep there.`;
}

/**
 * "Campgrounds on this route": the trail's campgrounds in route order, an
 * on-demand availability check for a stay, "Alert me" for stays that aren't
 * open, and a note for any part of the trip booked through another system.
 * Renders nothing for day hikes without campgrounds.
 */
export default function CampgroundsSection({
  trailId,
  typicalNights,
  data,
  failed,
  className,
}: {
  trailId: string;
  typicalNights: number | null;
  data: TrailCampgrounds | null;
  failed: boolean;
  className?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [today] = useState(() => localToday());
  const [stay, setStay] = useState<Stay>(
    () => stayFromParams(searchParams, today) ?? defaultStay(today, typicalNights),
  );
  const [result, setResult] = useState<{ key: string; data: TrailAvailability } | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alertSite, setAlertSite] = useState<{ site: TrailCampground; stay: Stay } | null>(null);
  const controller = useRef<AbortController | null>(null);
  const autoChecked = useRef(false);

  const view = campgroundView(data);
  const checkable = view.stops.some((stop) => stop.sites.some((site) => !site.retired && site.provider === "parks_canada"));

  const urlFor = useCallback(
    (s: Stay, extra: Record<string, string> = {}) =>
      `${pathname}?${new URLSearchParams({ id: trailId, ...stayParams(s), ...extra })}`,
    [pathname, trailId],
  );

  const check = useCallback(
    async (s: Stay) => {
      controller.current?.abort();
      const current = new AbortController();
      controller.current = current;
      setChecking(true);
      setError(null);
      try {
        const found = await checkTrailAvailability(trailId, s, current.signal);
        setResult({ key: JSON.stringify(s), data: found });
      } catch (caught) {
        if ((caught as { name?: string }).name === "AbortError") return;
        setError(caught instanceof ApiError ? caught.message : "We couldn't check availability right now.");
      } finally {
        if (controller.current === current) setChecking(false);
      }
    },
    [trailId],
  );

  const submit = () => {
    router.replace(urlFor(stay), { scroll: false });
    check(stay);
  };

  // A shared or returning link (?start=&nights=) checks straight away, and
  // ?alert=<site> (back from sign-in) reopens the alert dialog.
  useEffect(() => {
    if (autoChecked.current || !data || !checkable) return;
    const fromUrl = stayFromParams(searchParams, today);
    if (!fromUrl) return;
    autoChecked.current = true;
    const alertId = searchParams.get("alert");
    const site = data.campgrounds.find((c) => c.site_id === alertId && !c.retired);
    // Started from a callback rather than the effect body, so the state
    // updates land in their own render.
    Promise.resolve().then(() => {
      check(fromUrl);
      if (site) {
        setAlertSite({ site, stay: fromUrl });
        router.replace(urlFor(fromUrl), { scroll: false });
      }
    });
  }, [data, checkable, searchParams, today, check, router, urlFor]);

  useEffect(() => () => controller.current?.abort(), []);

  if (failed) {
    return (
      <section className={className} aria-labelledby="campgrounds-title">
        <h2 id="campgrounds-title" className={styles.title}>
          Campgrounds on this route
        </h2>
        <p className={styles.muted}>We couldn&apos;t load campgrounds right now. Try again shortly.</p>
      </section>
    );
  }
  if (!data || !view.visible) return null;

  const checkedResult = result?.key === JSON.stringify(stay) ? result.data : null;
  const availability = new Map((checkedResult?.campgrounds ?? []).map((found) => [found.site_id, found]));

  return (
    <section className={className} aria-labelledby="campgrounds-title">
      <h2 id="campgrounds-title" className={styles.title}>
        Campgrounds on this route
      </h2>
      {data.overnight_option && (
        <p className={styles.intro}>
          Usually done as a day hike, but you can stay overnight at{" "}
          {view.stops.length === 1 ? "the campground below" : "the campgrounds below"}.
        </p>
      )}

      {view.stops.length > 0 && (
        <>
          {view.parksCanada?.covers === "partial" && (
            <p className={styles.intro}>Parks Canada books part of this route.</p>
          )}
          {view.parksCanada?.note && <p className={styles.intro}>{view.parksCanada.note}</p>}

          {checkable && (
            <div className={styles.checkCard}>
              <StayForm stay={stay} today={today} busy={checking} onChange={setStay} onSubmit={submit} />
              <p className={styles.checkStatus} role="status" aria-live="polite">
                {error ? (
                  <span className={styles.checkError}>{error}</span>
                ) : checkedResult ? (
                  checkedStatus(checkedResult.checked_at)
                ) : (
                  "Check which campgrounds are free for your dates, or set an alert for ones that aren't."
                )}
              </p>
            </div>
          )}

          <ol className={styles.route}>
            {view.stops.map((stop, index) => (
              <StopRow
                key={stop.key}
                stop={stop}
                index={index}
                availability={availability}
                onAlert={(site) => setAlertSite({ site, stay })}
              />
            ))}
          </ol>
          {data.route_order_approximate && (
            <p className={styles.approximate}>Route order is approximate for some stops.</p>
          )}
          {data.booking_links.length > 0 && (
            <div className={styles.bookLinks}>
              {data.booking_links.map((link) => (
                <a key={link.url} className={styles.book} href={link.url} target="_blank" rel="noopener noreferrer">
                  {link.label}{" "}<span aria-hidden="true">↗</span>
                </a>
              ))}
              <p className={styles.bookHint}>Pick your campgrounds and dates there.</p>
            </div>
          )}
        </>
      )}

      {view.elsewhere.map((booking) => (
        <BookingNote key={booking.system} booking={booking} />
      ))}

      {alertSite && (
        <AlertDialog
          trailId={trailId}
          siteId={alertSite.site.site_id}
          campground={
            alertSite.site.stop_name && alertSite.site.site_code
              ? `${alertSite.site.stop_name} ${alertSite.site.site_code}`
              : alertSite.site.name
          }
          stay={alertSite.stay}
          returnTo={urlFor(alertSite.stay, { alert: alertSite.site.site_id })}
          onClose={() => setAlertSite(null)}
        />
      )}
    </section>
  );
}
