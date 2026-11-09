"use client";

import { useState } from "react";
import ui from "@/components/ui.module.css";
import { adminApi, type ReportStatus } from "@/lib/adminApi";
import { pageCount } from "@/lib/adminView";
import AdminFrame from "../AdminFrame";
import { useAdminData } from "../useAdminData";
import ReportItem from "./ReportItem";
import styles from "../admin.module.css";

const PER_PAGE = 20;
const FILTERS: { value: ReportStatus | "all"; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "resolved", label: "Resolved" },
  { value: "all", label: "All" },
];

function ReportsBody() {
  const [status, setStatus] = useState<ReportStatus | "all">("open");
  const [page, setPage] = useState(1);
  const { state, reload } = useAdminData(`reports:${status}:${page}`, (signal) =>
    adminApi.reports(status, page, PER_PAGE, signal),
  );
  const data = state.data;
  const pages = data ? pageCount(data.total, data.per_page) : 1;

  return (
    <section className={styles.card} aria-labelledby="reports-title">
      <div className={styles.cardHead}>
        <h2 id="reports-title" className={styles.cardTitle}>
          Profile, trip-note and post reports
        </h2>
        <div className={`${ui.segmented} ${styles.filters}`} role="group" aria-label="Show">
          {FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              aria-pressed={status === filter.value}
              onClick={() => {
                setStatus(filter.value);
                setPage(1);
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>
      <p className={`${styles.muted} ${styles.small}`}>
        Reports also arrive by email. Resolving one only closes it here; moderate the account from its page.
      </p>
      {state.status === "error" && (
        <p className={ui.error} role="alert">
          {state.message}
        </p>
      )}
      {!data && state.status === "loading" && <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />}
      {data && (
        <>
          {data.items.length === 0 ? (
            <p className={styles.empty}>{status === "open" ? "No open reports. All clear." : "No reports."}</p>
          ) : (
            <ul className={styles.list} aria-busy={state.status === "loading"}>
              {data.items.map((report) => (
                <ReportItem key={report.id} report={report} onChange={reload} />
              ))}
            </ul>
          )}
          {data.total > data.per_page && (
            <div className={styles.pager}>
              <span className={styles.muted}>
                Page {data.page} of {pages} · {data.total} reports
              </span>
              <span className={styles.pagerButtons}>
                <button type="button" className={ui.secondary} disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  Previous
                </button>
                <button type="button" className={ui.secondary} disabled={page >= pages} onClick={() => setPage(page + 1)}>
                  Next
                </button>
              </span>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default function AdminReportsPage() {
  return (
    <AdminFrame title="Reports">
      <ReportsBody />
    </AdminFrame>
  );
}
