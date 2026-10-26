"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import Dialog from "@/components/Dialog";
import HikeLogDialog from "@/components/HikeLogDialog";
import TrailBadge from "@/components/TrailBadge";
import ui from "@/components/ui.module.css";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { buildJournal } from "@/lib/journal";
import { searchTrails, type TrailListItem } from "@/lib/trailsApi";
import { useHikeLogs } from "@/lib/useHikeLogs";
import { useProfile } from "@/lib/useProfile";
import Book from "./Book";
import { useHikePhoto } from "@/lib/useHikePhoto";
import { formatHikeDate, renderJournalPage, type PageContext } from "./JournalPages";
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

export default function JournalPage() {
  const { status, user } = useAuth();
  const { profile } = useProfile();
  const hikeLogs = useHikeLogs();
  const guest = status !== "signedIn" && status !== "loading";
  const [catalogue, setCatalogue] = useState<TrailListItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [request, setRequest] = useState<{ page: number; seq: number } | null>(null);
  const [open, setOpen] = useState<{ log: HikeLog; colour: string; editing: boolean } | null>(null);
  const { stamped, mark } = useStamped(user?.id ?? null);

  useEffect(() => {
    const controller = new AbortController();
    searchTrails("", controller.signal, { limit: CATALOGUE_SIZE })
      .then(setCatalogue)
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, []);

  const logs = useMemo(() => (guest ? [] : hikeLogs.logs), [guest, hikeLogs.logs]);
  const journal = useMemo(() => (catalogue ? buildJournal(catalogue, logs) : null), [catalogue, logs]);
  const ready = journal && (guest || (status === "signedIn" && !hikeLogs.loading && stamped));

  const owner = profile?.display_name ?? user?.email?.split("@")[0] ?? null;
  const ctx: PageContext | null = journal
    ? {
        journal,
        logs: new Map(logs.map((log) => [log.trail.id, log])),
        owner,
        guest,
        stamped: stamped ?? new Set(),
        onStamped: mark,
        onOpenEntry: (log, colour) => setOpen({ log, colour, editing: false }),
        onJump: (page) => setRequest((r) => ({ page, seq: (r?.seq ?? 0) + 1 })),
      }
    : null;

  let body;
  if (failed) {
    body = <p className={styles.status}>We couldn&apos;t load the trail catalogue. Check your connection and try again.</p>;
  } else if (!ready || !ctx) {
    body = <div className={`${ui.skeleton} ${styles.bookSkeleton}`} aria-busy="true" aria-label="Loading your journal" />;
  } else {
    body = (
      <Book
        count={ctx.journal.pages.length}
        render={(index, active) => renderJournalPage(ctx, index, active)}
        request={request}
        label={guest ? "Trail Journal (sample)" : `${owner ?? "Your"} Trail Journal`}
      />
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        <header className={styles.intro}>
          <h1 className={styles.title}>Trail Journal</h1>
          <p className={styles.lede}>
            {guest
              ? "A scrapbook of every trail you hike. Sign in to start stamping yours."
              : "Your private scrapbook. Mark a trail as hiked from its page to stamp its badge."}
          </p>
          {hikeLogs.error && !guest && (
            <p className={ui.error} role="alert">
              {hikeLogs.error}
            </p>
          )}
        </header>
        {body}
      </div>

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
