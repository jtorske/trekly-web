"use client";

import { useState } from "react";
import Link from "next/link";
import ui from "@/components/ui.module.css";
import { adminApi, type AdminReport } from "@/lib/adminApi";
import { formatDateTime, timeAgo, whoLabel } from "@/lib/adminView";
import { toast } from "@/lib/toast";
import ConfirmDialog from "../ConfirmDialog";
import styles from "../admin.module.css";

/** One report: what was reported, links to the content, and resolve / reopen (confirmed, audited). */
export default function ReportItem({
  report,
  onChange,
  showReported = true,
}: {
  report: AdminReport;
  onChange: () => void;
  showReported?: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const [moderatingPost, setModeratingPost] = useState(false);
  const post = report.post ?? null;
  const resolving = report.status === "open";
  const reported = whoLabel(report.reported);
  const username = report.reported.username;

  return (
    <li className={styles.listItem}>
      <div className={styles.listRow}>
        <span>
          <strong>{report.kind === "post" ? "Activity post" : report.kind === "trip_note" ? "Trip note" : "Profile"}</strong>
          {showReported && (
            <>
              {" · "}
              <Link className={styles.link} href={`/admin/users/${report.reported.id}`}>
                {reported}
              </Link>
            </>
          )}
          {" · "}
          <span className={styles.pill}>{report.reason}</span>
        </span>
        <span className={styles.pills}>
          {report.reported_hidden && <span className={styles.pillWarn}>Profile hidden</span>}
          {post?.hidden && <span className={styles.pillWarn}>Post hidden</span>}
          <span className={report.status === "open" ? styles.pillDark : styles.pill}>{report.status === "open" ? "Open" : "Resolved"}</span>
        </span>
      </div>
      {report.kind === "trip_note" && (
        <span className={styles.small}>
          On {report.trail ? report.trail.name : "a trail that's since been removed"}
          {report.note ? ":" : " (the note has since been removed)"}
        </span>
      )}
      {report.note && <p className={styles.quote}>{report.note}</p>}
      {post && (
        <>
          <span className={styles.small}>
            {post.summary}
            {post.has_photo ? " (with a photo)" : ""}
            {post.note ? ":" : ""}
          </span>
          {post.note && <p className={styles.quote}>{post.note}</p>}
        </>
      )}
      {report.details && (
        <p className={styles.small}>
          <span className={styles.muted}>Reporter&apos;s details:</span> {report.details}
        </p>
      )}
      <span className={`${styles.muted} ${styles.small}`}>
        Reported by{" "}
        <Link className={styles.link} href={`/admin/users/${report.reporter.id}`}>
          {whoLabel(report.reporter)}
        </Link>{" "}
        <span title={formatDateTime(report.created_at)}>{timeAgo(report.created_at)}</span>
        {report.resolved_by && (
          <>
            {" · "}resolved by {whoLabel(report.resolved_by)} {timeAgo(report.resolved_at)}
          </>
        )}
      </span>
      <div className={styles.reportActions}>
        {username && !report.reported_hidden && (
          <Link className={styles.link} href={`/u/${username}`} target="_blank">
            View profile ↗
          </Link>
        )}
        {report.kind === "trip_note" && report.trail && (
          <Link className={styles.link} href={`/trails?id=${report.trail.id}`} target="_blank">
            View trail ↗
          </Link>
        )}
        {post?.trail && (
          <Link className={styles.link} href={`/trails?id=${post.trail.id}`} target="_blank">
            View trail ↗
          </Link>
        )}
        {post && (
          <button type="button" className={ui.secondary} onClick={() => setModeratingPost(true)}>
            {post.hidden ? "Unhide post" : "Hide post"}
          </button>
        )}
        {showReported && (
          <Link className={styles.link} href={`/admin/users/${report.reported.id}`}>
            Moderate {reported}
          </Link>
        )}
        <button type="button" className={resolving ? ui.primary : ui.ghost} onClick={() => setConfirming(true)}>
          {resolving ? "Mark resolved" : "Reopen"}
        </button>
      </div>
      {moderatingPost && post && (
        <ConfirmDialog
          confirmation={
            post.hidden
              ? {
                  title: "Show this post again?",
                  body: `It goes back to following ${reported}'s own sharing settings.`,
                  confirm: "Unhide post",
                  reason: false,
                  danger: false,
                }
              : {
                  title: "Hide this post?",
                  body: `Nobody sees it in the Activity feed, ${reported} included. Their hike and journal stay as they are.`,
                  confirm: "Hide post",
                  reason: true,
                  danger: true,
                }
          }
          onClose={() => setModeratingPost(false)}
          onConfirm={async (reason) => {
            await adminApi.setPostHidden(post.id, !post.hidden, reason);
            toast.success(post.hidden ? "Post visible again." : "Post hidden.");
            onChange();
          }}
        />
      )}
      {confirming && (
        <ConfirmDialog
          confirmation={{
            title: resolving ? "Mark this report resolved?" : "Reopen this report?",
            body: resolving
              ? `It moves out of the open queue. This doesn't change ${reported}'s profile; hide it or clear the username from their page first if needed.`
              : "It goes back into the open queue.",
            confirm: resolving ? "Mark resolved" : "Reopen",
            reason: false,
            danger: false,
          }}
          onClose={() => setConfirming(false)}
          onConfirm={async () => {
            await adminApi.setReportStatus(report.id, resolving ? "resolved" : "open");
            toast.success(resolving ? "Report resolved." : "Report reopened.");
            onChange();
          }}
        />
      )}
    </li>
  );
}
