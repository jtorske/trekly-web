import Link from "next/link";
import type { AuditEntry } from "@/lib/adminApi";
import { ACTION_LABELS, formatDateTime, timeAgo, whoLabel } from "@/lib/adminView";
import styles from "./admin.module.css";

/** Admin actions, newest first: what, on whom, by whom, when and why. */
export default function AuditList({ entries, showTarget = true }: { entries: AuditEntry[]; showTarget?: boolean }) {
  if (entries.length === 0) return <p className={styles.muted}>No admin actions yet.</p>;
  return (
    <ul className={styles.list}>
      {entries.map((entry) => (
        <li key={entry.id} className={styles.listItem}>
          <div className={styles.listRow}>
            <span>
              <strong>{ACTION_LABELS[entry.action]}</strong>
              {showTarget && entry.target_user && (
                <>
                  {" "}
                  <Link className={styles.link} href={`/admin/users/${entry.target_user.id}`}>
                    {whoLabel(entry.target_user)}
                  </Link>
                </>
              )}
              {entry.details.username && entry.action === "clear_username" && <> (was @{entry.details.username})</>}
            </span>
            <span className={`${styles.muted} ${styles.small}`} title={formatDateTime(entry.created_at)}>
              {timeAgo(entry.created_at)}
            </span>
          </div>
          <span className={`${styles.muted} ${styles.small}`}>
            by {whoLabel(entry.admin)}
            {entry.details.reason && <> · “{entry.details.reason}”</>}
          </span>
        </li>
      ))}
    </ul>
  );
}
