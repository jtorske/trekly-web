"use client";

import { Suspense } from "react";
import Link from "next/link";
import RequireAuth from "@/components/RequireAuth";
import ui from "@/components/ui.module.css";
import { SavedTrailList } from "@/app/profile/sections";
import { useSavedTrails } from "@/lib/useSavedTrails";
import styles from "@/app/profile/page.module.css";

function SavedTrailsContent() {
  const savedTrails = useSavedTrails();
  return (
    <main className={styles.page}>
      <div className={styles.texture} aria-hidden="true" />
      <div className={styles.wrap}>
        <Link href="/profile?tab=trails" className={ui.ghost}>
          ← Back to profile
        </Link>
        <h1 className={styles.name}>Saved trails</h1>
        <p className={styles.bio}>
          Trails you&apos;ve bookmarked. Saving a trail doesn&apos;t plan a trip or mark it as hiked.
        </p>
        <div className={styles.panel}>
          <SavedTrailList data={savedTrails} />
        </div>
      </div>
    </main>
  );
}

export default function SavedTrailsPage() {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <RequireAuth fallback={<main className={styles.page} aria-busy="true" />}>
        <SavedTrailsContent />
      </RequireAuth>
    </Suspense>
  );
}
