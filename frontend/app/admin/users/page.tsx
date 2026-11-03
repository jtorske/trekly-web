"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Avatar from "@/components/Avatar";
import ui from "@/components/ui.module.css";
import { adminApi, type AdminUser, type UserSort, type UsersQuery } from "@/lib/adminApi";
import {
  FILTER_LABELS,
  PER_PAGE,
  USER_FILTERS,
  VISIBILITY_LABELS,
  formatDate,
  formatDateTime,
  nextSort,
  pageCount,
  parseUsersQuery,
  providerLabel,
  timeAgo,
  usersQueryString,
} from "@/lib/adminView";
import AdminFrame from "../AdminFrame";
import { useAdminData } from "../useAdminData";
import styles from "../admin.module.css";

const COLUMNS: { key: UserSort | null; label: string; num?: boolean }[] = [
  { key: "name", label: "User" },
  { key: "email", label: "Email" },
  { key: null, label: "Sign-in" },
  { key: "joined", label: "Joined" },
  { key: "last_sign_in", label: "Last sign-in" },
  { key: "hikes", label: "Hikes", num: true },
  { key: "gear", label: "Gear", num: true },
  { key: "alerts", label: "Alerts", num: true },
  { key: null, label: "Profile" },
];

function StatusPills({ user }: { user: AdminUser }) {
  return (
    <span className={styles.pills}>
      <span className={user.visibility === "hidden" ? styles.pillWarn : styles.pill}>{VISIBILITY_LABELS[user.visibility]}</span>
      {user.banned && <span className={styles.pillWarn}>Banned</span>}
      {user.is_admin && <span className={styles.pillDark}>Admin</span>}
    </span>
  );
}

function UsersBody() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = parseUsersQuery(new URLSearchParams(params.toString()));
  const queryKey = usersQueryString(query);
  const [search, setSearch] = useState(query.q);

  const go = (next: UsersQuery) => router.replace(`${pathname}${usersQueryString(next)}`, { scroll: false });

  // Search as you type, a beat after the last keystroke.
  useEffect(() => {
    if (search.trim() === query.q.trim()) return;
    const timer = setTimeout(() => go({ ...query, q: search, page: 1 }), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const { state } = useAdminData(`users${queryKey}`, (signal) => adminApi.users(query, PER_PAGE, signal));
  const page = state.data;
  const pages = page ? pageCount(page.total, page.per_page) : 1;

  return (
    <section className={styles.card} aria-labelledby="users-title">
      <h2 id="users-title" className={ui.srOnly}>
        Users
      </h2>
      <div className={styles.toolbar}>
        <label className={`${ui.field} ${styles.search}`}>
          <span className={ui.srOnly}>Search users</span>
          <input
            className={ui.input}
            type="search"
            placeholder="Search name, @username, email or id"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            maxLength={100}
            spellCheck={false}
            autoCapitalize="none"
          />
        </label>
        <div className={`${ui.segmented} ${styles.filters}`} role="group" aria-label="Show">
          {USER_FILTERS.map((filter) => (
            <button
              key={filter}
              type="button"
              aria-pressed={query.filter === filter}
              onClick={() => go({ ...query, filter, page: 1 })}
            >
              {FILTER_LABELS[filter]}
            </button>
          ))}
        </div>
      </div>

      {state.status === "error" && (
        <p className={ui.error} role="alert">
          {state.message}
        </p>
      )}
      {!page && state.status === "loading" && <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />}

      {page && (
        <>
          <div className={styles.tableScroll}>
            <table className={styles.table} aria-busy={state.status === "loading"}>
              <thead>
                <tr>
                  {COLUMNS.map((column) => {
                    const sorted = column.key !== null && query.sort === column.key;
                    return (
                      <th
                        key={column.label}
                        scope="col"
                        className={column.num ? styles.num : undefined}
                        aria-sort={sorted ? (query.dir === "asc" ? "ascending" : "descending") : undefined}
                      >
                        {column.key ? (
                          <button type="button" className={styles.sortButton} onClick={() => go(nextSort(query, column.key as UserSort))}>
                            {column.label}
                            <span className={styles.sortArrow} aria-hidden="true">
                              {sorted ? (query.dir === "asc" ? "▲" : "▼") : ""}
                            </span>
                          </button>
                        ) : (
                          column.label
                        )}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {page.items.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <span className={styles.person}>
                        <Avatar path={user.avatar_path} name={user.display_name} email={user.email} size={32} />
                        <span>
                          <Link href={`/admin/users/${user.id}`} className={styles.personName}>
                            {user.display_name || user.email || "No name"}
                          </Link>
                          <span className={styles.personSub}>{user.username ? `@${user.username}` : "no username"}</span>
                        </span>
                      </span>
                    </td>
                    <td>{user.email ?? "—"}</td>
                    <td>
                      <span className={styles.pills}>
                        {user.providers.map((p) => (
                          <span key={p} className={styles.pill}>
                            {providerLabel(p)}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td className={styles.nowrap}>{formatDate(user.joined_at)}</td>
                    <td className={styles.nowrap} title={formatDateTime(user.last_sign_in_at)}>
                      {user.last_sign_in_at ? timeAgo(user.last_sign_in_at) : "Never"}
                    </td>
                    <td className={styles.num}>{user.hikes}</td>
                    <td className={styles.num}>{user.gear}</td>
                    <td className={styles.num}>{user.alerts}</td>
                    <td>
                      <StatusPills user={user} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {page.items.length === 0 && <p className={styles.empty}>No users match.</p>}
          </div>
          <div className={styles.pager}>
            <span className={styles.muted} aria-live="polite">
              {page.total === 0
                ? "0 users"
                : `${(page.page - 1) * page.per_page + 1}–${Math.min(page.page * page.per_page, page.total)} of ${page.total} users`}
            </span>
            <span className={styles.pagerButtons}>
              <button type="button" className={ui.secondary} disabled={query.page <= 1} onClick={() => go({ ...query, page: query.page - 1 })}>
                Previous
              </button>
              <button type="button" className={ui.secondary} disabled={query.page >= pages} onClick={() => go({ ...query, page: query.page + 1 })}>
                Next
              </button>
            </span>
          </div>
        </>
      )}
    </section>
  );
}

export default function AdminUsersPage() {
  return (
    <AdminFrame title="Users">
      <UsersBody />
    </AdminFrame>
  );
}
