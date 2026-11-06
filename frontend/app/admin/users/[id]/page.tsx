"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Avatar from "@/components/Avatar";
import ui from "@/components/ui.module.css";
import { adminApi, type AdminUserDetail, type UserAction } from "@/lib/adminApi";
import {
  VISIBILITY_LABELS,
  confirmationFor,
  formatDate,
  formatDateTime,
  providerLabel,
  timeAgo,
  whoLabel,
} from "@/lib/adminView";
import { toast } from "@/lib/toast";
import AdminFrame from "../../AdminFrame";
import AuditList from "../../AuditList";
import ConfirmDialog from "../../ConfirmDialog";
import ReportItem from "../../reports/ReportItem";
import { useAdminData } from "../../useAdminData";
import styles from "../../admin.module.css";

function Actions({ user, onDone }: { user: AdminUserDetail; onDone: () => void }) {
  const [pending, setPending] = useState<UserAction | null>(null);
  const who = whoLabel(user);
  const protectedAccount = user.is_admin;
  const buttons: { action: UserAction; label: string; show: boolean; disabled?: boolean; danger?: boolean }[] = [
    { action: "hide", label: "Hide profile", show: user.visibility !== "hidden" && user.username !== null, danger: true },
    { action: "unhide", label: "Unhide profile", show: user.visibility === "hidden" },
    { action: "clear-username", label: "Clear username", show: user.username !== null, danger: true },
    { action: "ban", label: "Ban", show: !user.banned, disabled: protectedAccount, danger: true },
    { action: "unban", label: "Unban", show: user.banned, disabled: protectedAccount },
    { action: "password-reset", label: "Send password reset", show: true, disabled: !user.email },
  ];
  return (
    <section className={styles.card} aria-labelledby="actions-title">
      <h2 id="actions-title" className={styles.cardTitle}>
        Actions
      </h2>
      <div className={styles.actions}>
        {buttons
          .filter((b) => b.show)
          .map((b) => (
            <button
              key={b.action}
              type="button"
              className={b.danger ? ui.danger : ui.secondary}
              disabled={b.disabled}
              onClick={() => setPending(b.action)}
            >
              {b.label}
            </button>
          ))}
      </div>
      <p className={`${styles.muted} ${styles.small} ${styles.spaced}`}>
        Every action asks first and is recorded in the audit log.{" "}
        {protectedAccount && "Admin accounts can't be banned here. "}
        Accounts are deleted only by their owners.
      </p>
      {pending && (
        <ConfirmDialog
          confirmation={confirmationFor(pending, who, user.email)}
          onClose={() => setPending(null)}
          onConfirm={async (reason) => {
            const result = await adminApi.act(user.id, pending, reason);
            toast.success(result.message);
            onDone();
          }}
        />
      )}
    </section>
  );
}

function Detail({ user, reload }: { user: AdminUserDetail; reload: () => void }) {
  return (
    <>
      <section className={styles.card} aria-labelledby="identity-title">
        <div className={styles.identity}>
          <Avatar path={user.avatar_path} name={user.display_name} email={user.email} size={64} />
          <div>
            <h2 id="identity-title" className={styles.identityName}>
              {user.display_name || user.email || "No name"}
            </h2>
            <span className={styles.muted}>
              {user.username ? (
                user.visibility === "public" ? (
                  <Link className={styles.link} href={`/u/${user.username}`}>
                    @{user.username}
                  </Link>
                ) : (
                  `@${user.username}`
                )
              ) : (
                "No username"
              )}
            </span>
          </div>
          <span className={styles.pills}>
            <span className={user.visibility === "hidden" ? styles.pillWarn : styles.pill}>{VISIBILITY_LABELS[user.visibility]}</span>
            {user.banned && <span className={styles.pillWarn}>Banned</span>}
            {user.is_admin && <span className={styles.pillDark}>Admin</span>}
          </span>
        </div>
        {user.bio && <p className={`${styles.quote} ${styles.spaced}`}>{user.bio}</p>}
        <dl className={styles.facts}>
          <div className={styles.fact}>
            <dt>Email</dt>
            <dd>{user.email ?? "—"}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Sign-in</dt>
            <dd>{user.providers.map(providerLabel).join(", ") || "—"}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Joined</dt>
            <dd>{formatDate(user.joined_at)}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Last sign-in</dt>
            <dd title={formatDateTime(user.last_sign_in_at)}>{user.last_sign_in_at ? timeAgo(user.last_sign_in_at) : "Never"}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Home region</dt>
            <dd>{user.home_region ?? "—"}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Hikes · gear · alerts</dt>
            <dd>
              {user.hikes} · {user.gear} · {user.alerts}
            </dd>
          </div>
          <div className={styles.fact}>
            <dt>Reports filed</dt>
            <dd>{user.reports_filed}</dd>
          </div>
          <div className={styles.fact}>
            <dt>User id</dt>
            <dd className={styles.small}>{user.id}</dd>
          </div>
          {user.hidden_at && (
            <div className={styles.fact}>
              <dt>Hidden</dt>
              <dd>
                {formatDate(user.hidden_at)}
                {user.hidden_reason && <> · “{user.hidden_reason}”</>}
              </dd>
            </div>
          )}
        </dl>
      </section>

      <Actions user={user} onDone={reload} />

      <div className={styles.grid2}>
        <section className={styles.card} aria-labelledby="hikes-title">
          <h2 id="hikes-title" className={styles.cardTitle}>
            Hikes ({user.hikes_list.length})
          </h2>
          {user.hikes_list.length === 0 ? (
            <p className={styles.muted}>No hikes logged.</p>
          ) : (
            <ul className={styles.list}>
              {user.hikes_list.map((hike) => (
                <li key={hike.id} className={styles.listItem}>
                  <div className={styles.listRow}>
                    <Link className={styles.link} href={`/trails?id=${hike.trail.id}`}>
                      {hike.trail.name}
                    </Link>
                    <span className={`${styles.muted} ${styles.small}`}>
                      {hike.hiked_on ? formatDate(hike.hiked_on) : "Before joining"}
                      {hike.verified && " · GPS verified"}
                      {hike.has_photo && " · photo"}
                    </span>
                  </div>
                  {hike.note && <p className={styles.quote}>{hike.note}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={styles.card} aria-labelledby="alerts-title">
          <h2 id="alerts-title" className={styles.cardTitle}>
            Alerts ({user.alerts_list.length})
          </h2>
          {user.alerts_list.length === 0 ? (
            <p className={styles.muted}>No availability alerts.</p>
          ) : (
            <ul className={styles.list}>
              {user.alerts_list.map((alert) => (
                <li key={alert.id} className={styles.listItem}>
                  <div className={styles.listRow}>
                    <strong>{alert.site_name}</strong>
                    <span className={alert.status === "active" ? styles.pillDark : styles.pill}>{alert.status}</span>
                  </div>
                  <span className={`${styles.muted} ${styles.small}`}>
                    {formatDate(alert.start_date)} · {alert.nights} night{alert.nights === 1 ? "" : "s"} · party of {alert.party_size}
                    {alert.trail && <> · {alert.trail.name}</>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className={styles.grid2}>
        <section className={styles.card} aria-labelledby="reports-title">
          <h2 id="reports-title" className={styles.cardTitle}>
            Reports about them ({user.reports_about.length})
          </h2>
          {user.reports_about.length === 0 ? (
            <p className={styles.muted}>No reports.</p>
          ) : (
            <ul className={styles.list}>
              {user.reports_about.map((report) => (
                <ReportItem key={report.id} report={report} onChange={reload} showReported={false} />
              ))}
            </ul>
          )}
        </section>
        <section className={styles.card} aria-labelledby="history-title">
          <h2 id="history-title" className={styles.cardTitle}>
            Admin history
          </h2>
          <AuditList entries={user.audit} showTarget={false} />
        </section>
      </div>
    </>
  );
}

function UserBody() {
  const { id } = useParams<{ id: string }>();
  const { state, reload } = useAdminData(`user:${id}`, (signal) => adminApi.user(id, signal));
  return (
    <>
      <Link href="/admin/users" className={styles.back}>
        <span aria-hidden="true">←</span> All users
      </Link>
      {state.status === "error" && (
        <p className={ui.error} role="alert">
          {state.message}
        </p>
      )}
      {state.data ? (
        <Detail user={state.data} reload={reload} />
      ) : (
        state.status === "loading" && <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />
      )}
    </>
  );
}

export default function AdminUserPage() {
  return (
    <AdminFrame title="User">
      <UserBody />
    </AdminFrame>
  );
}
