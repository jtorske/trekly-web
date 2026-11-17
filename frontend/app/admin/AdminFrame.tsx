"use client";

import { Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Flag, Image as ImageIcon, LayoutDashboard, ListChecks, Megaphone, Users, type LucideIcon } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { ApiError } from "@/lib/api";
import { adminApi } from "@/lib/adminApi";
import styles from "./admin.module.css";

const TABS: { href: string; label: string; icon: LucideIcon; exact?: boolean }[] = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/moderation", label: "Moderation", icon: Flag },
  { href: "/admin/photos", label: "Trail photos", icon: ImageIcon },
  { href: "/admin/trekly-posts", label: "Post queue", icon: ListChecks },
  { href: "/admin/posts", label: "Write a post", icon: Megaphone },
];

/**
 * The admin tabs: one row that scrolls sideways on a phone, fading at an edge
 * with more tabs past it (like the profile tabs).
 */
function AdminNav() {
  const pathname = usePathname();
  const listRef = useRef<HTMLElement>(null);
  const [fade, setFade] = useState({ start: false, end: false });

  const measure = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    setFade({
      start: list.scrollLeft > 1,
      end: list.scrollLeft + list.clientWidth < list.scrollWidth - 1,
    });
  }, []);

  useLayoutEffect(measure, [measure, pathname]);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    // Web fonts change the tab widths once they load.
    document.fonts?.ready.then(measure).catch(() => undefined);
    return () => observer.disconnect();
  }, [measure]);

  // Keep the current tab in view (e.g. Trail photos on a phone).
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [pathname]);

  return (
    <div className={styles.tabBar} data-fade-start={fade.start || undefined} data-fade-end={fade.end || undefined}>
      <nav ref={listRef} className={styles.tabs} aria-label="Admin" onScroll={measure}>
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
    </div>
  );
}

type Gate = { status: "checking" } | { status: "forbidden" } | { status: "error"; message: string } | { status: "admin" };

// The account the API last confirmed as an admin. Each admin page has its own
// frame, so without this every tab click waited on /api/admin/me again
// (~120 ms) before showing anything. The API still checks every request.
let confirmedAdmin: string | null = null;

/** Renders `children` only once the API confirms this account is an admin. */
function AdminGate({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [gate, setGate] = useState<Gate>(() =>
    userId !== null && confirmedAdmin === userId ? { status: "admin" } : { status: "checking" },
  );
  const known = gate.status === "admin" && confirmedAdmin === userId;

  const check = useCallback((signal?: AbortSignal) => {
    adminApi
      .me(signal)
      .then(() => {
        confirmedAdmin = userId;
        setGate({ status: "admin" });
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name === "AbortError") return;
        confirmedAdmin = null;
        if (error instanceof ApiError && error.status === 403) setGate({ status: "forbidden" });
        else setGate({ status: "error", message: error instanceof Error ? error.message : "That didn't load." });
      });
  }, [userId]);

  useEffect(() => {
    if (known) return;
    const controller = new AbortController();
    check(controller.signal);
    return () => controller.abort();
  }, [check, known]);

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
