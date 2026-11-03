"use client";

import Link from "next/link";
import ui from "@/components/ui.module.css";
import { adminApi, type Overview } from "@/lib/adminApi";
import { formatDate, formatDateTime, timeAgo } from "@/lib/adminView";
import AuditList from "./AuditList";
import AdminFrame from "./AdminFrame";
import { useAdminData } from "./useAdminData";
import styles from "./admin.module.css";

const NUMBER = new Intl.NumberFormat("en-CA");

function SignupChart({ weeks }: { weeks: Overview["signups_by_week"] }) {
  const max = Math.max(1, ...weeks.map((w) => w.count));
  const total = weeks.reduce((sum, w) => sum + w.count, 0);
  const latest = weeks[weeks.length - 1];
  return (
    <section className={styles.card} aria-labelledby="signups-title">
      <div className={styles.cardHead}>
        <h2 id="signups-title" className={styles.cardTitle}>
          Sign-ups per week
        </h2>
        <span className={`${styles.muted} ${styles.small}`}>
          {NUMBER.format(total)} in {weeks.length} weeks · {NUMBER.format(latest?.count ?? 0)} this week
        </span>
      </div>
      <div className={styles.chart} style={{ ["--bars" as string]: weeks.length }} role="list" aria-label="Sign-ups per week">
        {weeks.map((week) => {
          const height = `${(week.count / max) * 100}%`;
          const label = `Week of ${formatDate(week.week_start)}: ${week.count} sign-up${week.count === 1 ? "" : "s"}`;
          return (
            <div
              key={week.week_start}
              className={styles.bar}
              role="listitem"
              tabIndex={0}
              aria-label={label}
              style={{ ["--h" as string]: height }}
            >
              <span className={styles.barFill} style={{ height }} />
              <span className={styles.barTip} aria-hidden="true">
                <strong>{week.count}</strong> · week of {formatDate(week.week_start)}
              </span>
            </div>
          );
        })}
      </div>
      <div className={styles.axis} style={{ ["--bars" as string]: weeks.length }} aria-hidden="true">
        {weeks.map((week, index) => (
          <span key={week.week_start}>{index % 3 === 0 || index === weeks.length - 1 ? formatDate(week.week_start).replace(/, \d{4}$/, "") : ""}</span>
        ))}
      </div>
      <details className={styles.details}>
        <summary>Show as a table</summary>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Week of</th>
              <th scope="col" className={styles.num}>
                Sign-ups
              </th>
            </tr>
          </thead>
          <tbody>
            {weeks.map((week) => (
              <tr key={week.week_start}>
                <td>{formatDate(week.week_start)}</td>
                <td className={styles.num}>{week.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

function Poller({ poller }: { poller: Overview["poller"] }) {
  return (
    <section className={styles.card} aria-labelledby="poller-title">
      <div className={styles.cardHead}>
        <h2 id="poller-title" className={styles.cardTitle}>
          Alert poller
        </h2>
        {poller?.running && <span className={styles.pillDark}>Running now</span>}
      </div>
      {poller ? (
        <dl className={styles.facts}>
          <div className={styles.fact}>
            <dt>Last finished</dt>
            <dd>
              {timeAgo(poller.last_finished_at)}
              <span className={`${styles.personSub}`}>{formatDateTime(poller.last_finished_at)}</span>
            </dd>
          </div>
          <div className={styles.fact}>
            <dt>Last started</dt>
            <dd>{formatDateTime(poller.last_started_at)}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Result</dt>
            <dd>{poller.last_result ?? "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className={styles.muted}>The poller hasn&apos;t run on this database yet.</p>
      )}
    </section>
  );
}

function OverviewBody() {
  const { state } = useAdminData("overview", (signal) =>
    Promise.all([adminApi.overview(signal), adminApi.audit(1, 8, signal)]),
  );
  if (!state.data) {
    if (state.status === "error")
      return (
        <p className={ui.error} role="alert">
          {state.message}
        </p>
      );
    return <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />;
  }
  const [overview, audit] = state.data;
  const tiles: { label: string; value: number; note?: string; href?: string }[] = [
    { label: "Users", value: overview.users_total, href: "/admin/users" },
    {
      label: "New this week",
      value: overview.signups_by_week[overview.signups_by_week.length - 1]?.count ?? 0,
      href: "/admin/users",
    },
    { label: "Hikes logged", value: overview.hikes_total },
    { label: "Active alerts", value: overview.active_alerts },
    {
      label: "Open reports",
      value: overview.open_reports,
      note: overview.open_reports ? "Needs a look" : "All clear",
      href: "/admin/reports",
    },
  ];
  return (
    <>
      <div className={styles.tiles}>
        {tiles.map((tile) => {
          const body = (
            <>
              <span className={styles.tileLabel}>{tile.label}</span>
              <span className={styles.tileValue}>{NUMBER.format(tile.value)}</span>
              {tile.note && <span className={styles.tileNote}>{tile.note}</span>}
            </>
          );
          return tile.href ? (
            <Link key={tile.label} href={tile.href} className={styles.tile}>
              {body}
            </Link>
          ) : (
            <div key={tile.label} className={styles.tile}>
              {body}
            </div>
          );
        })}
      </div>
      <SignupChart weeks={overview.signups_by_week} />
      <div className={styles.grid2}>
        <Poller poller={overview.poller} />
        <section className={styles.card} aria-labelledby="audit-title">
          <h2 id="audit-title" className={styles.cardTitle}>
            Recent admin actions
          </h2>
          <AuditList entries={audit.items} />
        </section>
      </div>
    </>
  );
}

export default function AdminOverviewPage() {
  return (
    <AdminFrame title="Overview">
      <OverviewBody />
    </AdminFrame>
  );
}
