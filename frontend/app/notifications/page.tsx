"use client";

import { Suspense } from "react";
import RequireAuth from "@/components/RequireAuth";
import NotificationsPanel from "@/components/social/NotificationsPanel";
import ui from "@/components/ui.module.css";
import styles from "./page.module.css";

/** All notifications: where the phone menu's Notifications row leads. */
export default function NotificationsPage() {
  const skeleton = <div className={`${ui.skeleton} ${styles.skeleton}`} aria-busy="true" aria-label="Loading" />;
  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <h1 className={styles.title}>Notifications</h1>
        <div className={styles.card}>
          <Suspense fallback={skeleton}>
            <RequireAuth fallback={skeleton}>
              <NotificationsPanel />
            </RequireAuth>
          </Suspense>
        </div>
      </div>
    </main>
  );
}
