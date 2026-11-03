"use client";

import { Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Flag, Image as ImageIcon, LayoutDashboard, Users, type LucideIcon } from "lucide-react";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import styles from "./admin.module.css";

const TABS: { href: string; label: string; icon: LucideIcon; exact?: boolean }[] = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/reports", label: "Reports", icon: Flag },
  { href: "/admin/photos", label: "Trail photos", icon: ImageIcon },
];

function AdminNav() {
  const pathname = usePathname();
  return (
    <nav className={styles.tabs} aria-label="Admin">
      {TABS.map(({ href, label, icon: Icon, exact }) => {
        const current = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link key={href} href={href} className={styles.tab} aria-current={current ? "page" : undefined}>
            <Icon size={16} aria-hidden="true" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

type Gate = { status: "checking" } | { status: "forbidden" } | { status: "error"; message: string } | { status: "admin" };

/** Renders `children` only once the API confirms this account is an admin. */
function AdminGate({ children }: { children: ReactNode }) {
  const [gate, setGate] = useState<Gate>({ status: "checking" });

  const check = useCallback((signal?: AbortSignal) => {
    adminApi
      .me(signal)
      .then(() => setGate({ status: "admin" }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        if (error instanceof ApiError && error.status === 403) setGate({ status: "forbidden" });
        else setGate({ status: "error", message: error instanceof Error ? error.message : "That didn't load." });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    check(controller.signal);
    return () => controller.abort();
  }, [check]);

  if (gate.status === "checking") return <div className={`${ui.skeleton} ${styles.gateSkeleton}`} aria-busy="true" aria-label="Loading" />;
  if (gate.status === "forbidden") return <p className={ui.notice}>This area is only for Trekly admins.</p>;
  if (gate.status === "error")
    return (
      <p className={ui.error} role="alert">
        {gate.message}{" "}
        <button type="button" className={ui.ghost} onClick={() => { setGate({ status: "checking" }); check(); }}>
          Try again
        </button>
      </p>
    );
  return (
    <>
      <AdminNav />
      {children}
    </>
  );
}

/**
 * Every admin page: the header, then the admin tabs and the content once the
 * backend has confirmed the account is an admin (others see neither). The backend checks again
 * on every request; this only decides what to show.
 */
export default function AdminFrame({ title, children }: { title: string; children: ReactNode }) {
  const header = (
    <header className={styles.header}>
      <p className={styles.eyebrow}>Trekly admin</p>
      <h1 className={styles.title}>{title}</h1>
    </header>
  );
  const shell = (body: ReactNode) => (
    <main className={styles.page}>
      <div className={styles.wrap}>
        {header}
        {body}
      </div>
    </main>
  );
  return (
    <Suspense fallback={shell(null)}>
      <RequireAuth fallback={shell(null)}>{shell(<AdminGate>{children}</AdminGate>)}</RequireAuth>
    </Suspense>
  );
}
