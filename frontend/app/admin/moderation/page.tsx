"use client";

import { useState } from "react";
import ui from "@/components/ui.module.css";
import { pageCount } from "@/lib/adminView";
import { moderationApi, type ModerationSort, type ModerationView } from "@/lib/moderationAdminApi";
import AdminFrame from "../AdminFrame";
import { useAdminData } from "../useAdminData";
import ModerationCard from "./ModerationCard";
import styles from "../admin.module.css";
import page from "./page.module.css";

const PER_PAGE = 20;
const VIEWS: { value: ModerationView; label: string }[] = [
  { value: "queue", label: "Queue" },
  { value: "held", label: "Held" },
  { value: "hidden", label: "Hidden" },
  { value: "all", label: "All" },
];
const SORTS: { value: ModerationSort; label: string }[] = [
  { value: "newest", label: "Newest" },
  { value: "most_reported", label: "Most reported" },
];

function ModerationBody() {
  const [view, setView] = useState<ModerationView>("queue");
  const [sort, setSort] = useState<ModerationSort>("newest");
  const [pageNumber, setPage] = useState(1);
  const { state, reload } = useAdminData(`moderation:${view}:${sort}:${pageNumber}`, (signal) =>
    moderationApi.list(view, sort, pageNumber, PER_PAGE, signal),
  );
  const data = state.data;
  const pages = data ? pageCount(data.total, data.per_page) : 1;

  return (
    <section className={styles.card} aria-labelledby="moderation-title">
      <div className={styles.cardHead}>
        <h2 id="moderation-title" className={styles.cardTitle}>
          Held and reported content{data ? ` · ${data.queue_total} in the queue` : ""}
        </h2>
        <div className={page.controls}>
          <div className={`${ui.segmented} ${styles.filters}`} role="group" aria-label="Show">
            {VIEWS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={view === option.value}
                onClick={() => {
                  setView(option.value);
                  setPage(1);
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className={`${ui.segmented} ${styles.filters}`} role="group" aria-label="Sort">
            {SORTS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={sort === option.value}
                onClick={() => {
                  setSort(option.value);
                  setPage(1);
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <p className={`${styles.muted} ${styles.small}`}>
        Content the automated check flagged, published while it was down, or that people reported. Child-safety
        items always come first. Every action is audited; hiding and warnings email the author.
      </p>
      {state.status === "error" && (
        <p className={ui.error} role="alert">
          {state.message}
        </p>
      )}
      {!data && state.status === "loading" && (
        <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />
      )}
      {data && (
        <>
          {data.items.length === 0 ? (
            <p className={styles.empty}>{view === "queue" ? "Nothing waiting. All clear." : "Nothing here."}</p>
          ) : (
            <ul className={styles.list} aria-busy={state.status === "loading"}>
              {data.items.map((item) => (
                <ModerationCard key={item.id} item={item} onChange={reload} />
              ))}
            </ul>
          )}
          {data.total > data.per_page && (
            <div className={styles.pager}>
              <span className={styles.muted}>
                Page {data.page} of {pages} · {data.total} items
              </span>
              <span className={styles.pagerButtons}>
                <button type="button" className={ui.secondary} disabled={pageNumber <= 1} onClick={() => setPage(pageNumber - 1)}>
                  Previous
                </button>
                <button type="button" className={ui.secondary} disabled={pageNumber >= pages} onClick={() => setPage(pageNumber + 1)}>
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

export default function AdminModerationPage() {
  return (
    <AdminFrame title="Moderation">
      <ModerationBody />
    </AdminFrame>
  );
}
