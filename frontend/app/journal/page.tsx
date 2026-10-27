"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import Dialog from "@/components/Dialog";
import HikeLogDialog from "@/components/HikeLogDialog";
import TrailBadge from "@/components/TrailBadge";
import ui from "@/components/ui.module.css";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { buildJournal, sectionIndex } from "@/lib/journal";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useProfile } from "@/lib/useProfile";
import { useUnits } from "@/lib/useUnits";
import Book from "./Book";
import { useHikePhoto } from "@/lib/useHikePhoto";
import { formatHikeDate, GuestCover, renderJournalPage, type PageContext } from "./JournalPages";
import styles from "./journal.module.css";

const CATALOGUE_SIZE = 100;
const stampKey = (userId: string) => `trekly:journal-stamped:${userId}`;

function readStamped(userId: string): Set<string> {
  try {
    const ids = JSON.parse(window.localStorage.getItem(stampKey(userId)) ?? "[]");
    return new Set(Array.isArray(ids) ? ids : []);
  } catch {
    // Storage blocked or corrupt: stamps replay, which is harmless.
    return new Set();
  }
}

/**
 * Trails whose stamp animation has already played for this user, on this
 * device (a per-viewer nicety, so plain localStorage). Null until known.
 */
function useStamped(userId: string | null) {
  // userId is null during server render and hydration (auth restores on the
  // client), so reading storage here never causes a mismatch.
  const stored = useMemo(() => (userId ? readStamped(userId) : null), [userId]);
  const [marked, setMarked] = useState<{ userId: string; ids: Set<string> } | null>(null);
  const stamped = marked && marked.userId === userId ? marked.ids : stored;
  // Several stamps finish in the same frame; each must add to the latest set.
  const latest = useRef(stamped);
  useEffect(() => {
    latest.current = stamped;
  }, [stamped]);

  const mark = useCallback(
    (trailId: string) => {
      const current = latest.current;
      if (!userId || !current || current.has(trailId)) return;
      const ids = new Set(current).add(trailId);
      latest.current = ids;
      try {
        window.localStorage.setItem(stampKey(userId), JSON.stringify([...ids]));
      } catch {
        // See readStamped.
      }
      setMarked({ userId, ids });
    },
    [userId],
  );
  return { stamped, mark };
}

function EntryDialog({
  log,
  colour,
  onEdit,
  onClose,
}: {
  log: HikeLog;
  colour: string;
  onEdit: () => void;
  onClose: () => void;
}) {
  const photo = useHikePhoto(log.photo_path);
  return (
    <Dialog
      title={log.trail.name}
      subtitle={`Hiked ${formatHikeDate(log.hiked_on, "long")}`}
      onClose={onClose}
      footer={
        <>
          <Link href={`/trails?id=${encodeURIComponent(log.trail.id)}`} className={ui.ghost}>
            View trail
          </Link>
          <button type="button" className={ui.primary} onClick={onEdit} data-autofocus>
            Edit entry
          </button>
        </>
      }
    >
      <div className={styles.entry}>
        <figure className={styles.polaroid}>
          <div className={styles.polaroidPhoto}>
            {log.photo_path ? (
              // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
              photo ? <img src={photo} alt={`Your photo from ${log.trail.name}`} /> : <span className={styles.photoLoading} />
            ) : (
              <TrailBadge name={log.trail.name} terrain={log.trail.terrain} colour={colour} hiked className={styles.polaroidBadge} />
            )}
          </div>
          <figcaption className={styles.handwriting}>{log.note ?? formatHikeDate(log.hiked_on, "long")}</figcaption>
        </figure>
        {log.trail.retired_at && <p className={ui.hint}>This trail has left the Trekly catalogue. Your badge stays in your journal.</p>}
      </div>
    </Dialog>
  );
}

function Journal() {
  const { status, user } = useAuth();
  const { profile } = useProfile();
  const hikeLogs = useHikeLogs();
  const router = useRouter();
  const params = useSearchParams();
  const signedIn = status === "signedIn";
  const guest = status !== "signedIn" && status !== "loading";
  const [catalogue, setCatalogue] = useState<TrailListItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<{ log: HikeLog; colour: string; editing: boolean } | null>(null);
  const { stamped, mark } = useStamped(user?.id ?? null);
  // Whether the current section was opened from the contents in this visit,
  // so "Back to contents" can step back through history instead of adding to it.
  const [fromContents, setFromContents] = useState(false);

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    searchTrails("", controller.signal, { limit: CATALOGUE_SIZE })
      .then(setCatalogue)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [signedIn]);

  const [units] = useUnits();
  const journal = useMemo(
    () => (catalogue ? buildJournal(catalogue, hikeLogs.logs, units) : null),
    [catalogue, hikeLogs.logs, units],
  );
  const ready = journal && signedIn && !hikeLogs.loading && stamped;
  const at = journal ? sectionIndex(journal, params.get("section")) : 0;

  const openSection = useCallback(
    (slug: string | null) => {
      if (slug) {
        setFromContents(true);
        router.push(`/journal?section=${encodeURIComponent(slug)}`, { scroll: false });
      } else if (fromContents) {
        setFromContents(false);
        router.back();
      } else {
        router.replace("/journal", { scroll: false });
      }
    },
    [router, fromContents],
  );

  const owner = profile?.display_name ?? user?.email?.split("@")[0] ?? null;
  const ctx: PageContext | null = journal
    ? {
        journal,
        logs: new Map(hikeLogs.logs.map((log) => [log.trail.id, log])),
        owner,
        stamped: stamped ?? new Set(),
        onStamped: mark,
        onOpenEntry: (log, colour) => setOpen({ log, colour, editing: false }),
        onOpen: openSection,
      }
    : null;

  let body;
  if (guest) {
    body = (
      <section className={styles.bookArea} aria-label="Trail Journal">
        <div className={styles.coverStage}>
          <GuestCover />
        </div>
      </section>
    );
  } else if (failed) {
    body = <p className={styles.status}>We couldn&apos;t load the trail catalogue. Check your connection and try again.</p>;
  } else if (!ready || !ctx) {
    body = (
      <div className={styles.bookArea}>
        <div className={`${ui.skeleton} ${styles.bookSkeleton}`} aria-busy="true" aria-label="Loading your journal" />
      </div>
    );
  } else {
    body = (
      <Book
        count={ctx.journal.sections.length}
        at={at}
        render={(index, view, active) => renderJournalPage(ctx, index, view, active)}
        name={(index) => ctx.journal.sections[index].title}
        label={`${owner ?? "Your"} Trail Journal`}
      />
    );
  }

  return (
    <main className={styles.page}>
      <h1 className={styles.srOnly}>Trail Journal</h1>
      {hikeLogs.error && signedIn && (
        <p className={`${ui.error} ${styles.notice}`} role="alert">
          {hikeLogs.error}
        </p>
      )}
      {body}

      {open && !open.editing && (
        <EntryDialog log={open.log} colour={open.colour} onClose={() => setOpen(null)} onEdit={() => setOpen({ ...open, editing: true })} />
      )}
      {open?.editing && (
        <HikeLogDialog
          trailName={open.log.trail.name}
          entry={hikeLogs.byTrail.get(open.log.trail.id) ?? open.log}
          onSave={(input) => hikeLogs.save(open.log.trail.id, input)}
          onRemove={() => hikeLogs.remove(open.log.trail.id)}
          onClose={() => setOpen(null)}
        />
      )}
    </main>
  );
}

export default function JournalPage() {
  // useSearchParams needs a Suspense boundary for the static build.
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <Journal />
    </Suspense>
  );
}
