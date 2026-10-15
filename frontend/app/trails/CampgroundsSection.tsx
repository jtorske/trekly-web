import type { TrailBooking, TrailCampgrounds } from "@/lib/trailsApi";
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

function StopRow({ stop, index }: { stop: Stop; index: number }) {
  const first = stop.sites[0];
  const isGroup = stop.sites.length > 1;
  const code = isGroup ? null : first.site_code;
  const facts = isGroup ? [] : capacityFacts(first);
  const notes = [...new Set(stop.sites.map((site) => site.notes).filter(Boolean))];

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
        <p className={styles.meta}>
          {[first.park?.name, ...facts].filter(Boolean).join(" · ")}
        </p>
        {isGroup && (
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
        {stop.retired && <p className={styles.retiredNote}>No longer listed by Parks Canada</p>}
      </div>
    </li>
  );
}

/**
 * "Campgrounds on this route": the trail's campgrounds in route order, plus a
 * note for any part of the trip booked through another system. Renders
 * nothing for day hikes without campgrounds.
 */
export default function CampgroundsSection({
  data,
  failed,
  className,
}: {
  data: TrailCampgrounds | null;
  failed: boolean;
  className?: string;
}) {
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
  const view = campgroundView(data);
  if (!data || !view.visible) return null;

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
          <ol className={styles.route}>
            {view.stops.map((stop, index) => (
              <StopRow key={stop.key} stop={stop} index={index} />
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
    </section>
  );
}
