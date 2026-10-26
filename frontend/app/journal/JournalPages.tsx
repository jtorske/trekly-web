"use client";

import Link from "next/link";
import TrailBadge from "@/components/TrailBadge";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { BADGE_COLOURS, type Journal, type JournalGroup, type JournalPage, type Milestone } from "@/lib/journal";
import { useHikePhoto } from "@/lib/useHikePhoto";
import type { TrailListItem } from "@/lib/trailsApi";
import styles from "./journal.module.css";

export const formatHikeDate = (iso: string, month: "short" | "long" = "short") =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month, day: "numeric", year: "numeric" });

export interface PageContext {
  journal: Journal;
  logs: Map<string, HikeLog>;
  owner: string | null;
  guest: boolean;
  stamped: Set<string>;
  onStamped: (trailId: string) => void;
  onOpenEntry: (log: HikeLog, colour: string) => void;
  onJump: (page: number) => void;
}

function Folio({ page }: { page: number }) {
  return <span className={styles.folio}>{page}</span>;
}

function Cover({ ctx }: { ctx: PageContext }) {
  const { journal, owner, guest } = ctx;
  const percent = journal.total ? Math.round((journal.hiked / journal.total) * 100) : 0;
  return (
    <div className={styles.cover}>
      <div className={styles.coverFrame}>
        <p className={styles.coverEyebrow}>Trekly</p>
        <h1 className={styles.coverTitle}>Trail Journal</h1>
        <svg viewBox="0 0 120 40" className={styles.coverMark} aria-hidden="true">
          <path d="M4 36 34 10l12 12 18-18 26 24 10-8 16 16Z" />
        </svg>
        {guest ? (
          <div className={styles.coverGuest}>
            <p>Every trail you hike earns a stamp in this book.</p>
            <Link href="/login?next=%2Fjournal" className={styles.coverButton}>
              Sign in to start your journal
            </Link>
            <p className={styles.coverSmall}>
              New to Trekly? <Link href="/signup?next=%2Fjournal">Create an account</Link>
            </p>
          </div>
        ) : (
          <div className={styles.coverOwner}>
            {owner && <p className={styles.coverName}>{owner}</p>}
            <p className={styles.coverProgress}>
              <strong>{journal.hiked}</strong> / {journal.total} trails
            </p>
            <div className={styles.coverBar} role="progressbar" aria-valuemin={0} aria-valuemax={journal.total} aria-valuenow={journal.hiked} aria-label="Trails hiked">
              <span style={{ width: `${percent}%` }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function hikedIn(group: JournalGroup, logs: Map<string, HikeLog>) {
  return group.trails.filter((trail) => logs.has(trail.id)).length;
}

function Contents({ ctx, groups, part, index }: { ctx: PageContext; groups: JournalGroup[]; part: 0 | 1; index: number }) {
  return (
    <div className={styles.paperInner}>
      <h2 className={styles.pageTitle}>{part === 0 ? "Contents" : "Contents, continued"}</h2>
      <ol className={styles.contents}>
        {groups.map((group) => {
          const start = ctx.journal.groupStart.get(group.key) ?? 0;
          return (
            <li key={group.key}>
              <button type="button" className={styles.contentsRow} onClick={() => ctx.onJump(start)}>
                <span className={styles.contentsDot} style={{ background: group.colour }} aria-hidden="true" />
                <span className={styles.contentsName}>{group.title}</span>
                <span className={styles.contentsCount}>
                  {hikedIn(group, ctx.logs)}/{group.trails.length}
                </span>
                <span className={styles.contentsLeader} aria-hidden="true" />
                <span className={styles.contentsPage}>
                  <span className={styles.srOnly}>page </span>
                  {start}
                </span>
              </button>
            </li>
          );
        })}
        {part === 1 && (
          <li>
            <button type="button" className={styles.contentsRow} onClick={() => ctx.onJump(ctx.journal.pages.length - 2)}>
              <span className={styles.contentsDot} style={{ background: "var(--color-tan)" }} aria-hidden="true" />
              <span className={styles.contentsName}>Milestones</span>
              <span className={styles.contentsLeader} aria-hidden="true" />
              <span className={styles.contentsPage}>{ctx.journal.pages.length - 2}</span>
            </button>
          </li>
        )}
      </ol>
      {part === 1 && (
        <div className={styles.legend}>
          <p className={styles.legendTitle}>Badge shapes</p>
          <ul>
            {(["easy", "moderate", "difficult", "extreme"] as const).map((terrain) => (
              <li key={terrain}>
                <TrailBadge name="" terrain={terrain} colour={BADGE_COLOURS[0]} hiked className={styles.legendBadge} />
                <span>{terrain[0].toUpperCase() + terrain.slice(1)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Folio page={index} />
    </div>
  );
}

function Slot({ trail, group, ctx, active }: { trail: TrailListItem; group: JournalGroup; ctx: PageContext; active: boolean }) {
  const log = ctx.logs.get(trail.id);
  const photo = useHikePhoto(log?.photo_path ?? null);
  const href = `/trails?id=${encodeURIComponent(trail.id)}`;

  if (!log) {
    return (
      <Link href={href} className={styles.slotCell} aria-label={`${trail.name}: not hiked yet. Open the trail`}>
        <TrailBadge name={trail.name} terrain={trail.terrain} colour={group.colour} hiked={false} className={styles.badge} />
        <span className={styles.slotCaption}>Not yet</span>
      </Link>
    );
  }

  const stamp = active && !ctx.stamped.has(trail.id);
  return (
    <button
      type="button"
      className={styles.slotCell}
      onClick={() => ctx.onOpenEntry(log, group.colour)}
      aria-label={`${trail.name}: hiked ${formatHikeDate(log.hiked_on, "long")}. Open journal entry`}
    >
      <span className={styles.badgeWrap}>
        {log.photo_path && (
          <span className={styles.miniPolaroid} aria-hidden="true">
            {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL */}
            {photo ? <img src={photo} alt="" /> : <span className={styles.photoLoading} />}
          </span>
        )}
        {!log.photo_path && log.note && (
          <span className={styles.miniNote} aria-hidden="true">
            {log.note}
          </span>
        )}
        <TrailBadge
          name={trail.name}
          terrain={trail.terrain}
          colour={group.colour}
          hiked
          stamp={stamp}
          onStamped={() => ctx.onStamped(trail.id)}
          className={styles.badge}
        />
      </span>
      <span className={`${styles.slotCaption} ${styles.slotDate}`}>{formatHikeDate(log.hiked_on)}</span>
    </button>
  );
}

function GroupPage({ ctx, page, index, active }: { ctx: PageContext; page: Extract<JournalPage, { kind: "group" }>; index: number; active: boolean }) {
  const { group } = page;
  return (
    <div className={styles.paperInner}>
      {page.part === 0 ? (
        <header className={styles.groupHeader}>
          <span className={styles.tape} style={{ background: group.colour }} aria-hidden="true" />
          <h2 className={styles.pageTitle}>{group.title}</h2>
          <p className={styles.groupMeta}>
            {group.subtitle && <span>{group.subtitle} · </span>}
            {hikedIn(group, ctx.logs)} of {group.trails.length} hiked
          </p>
        </header>
      ) : (
        <p className={styles.runningHead}>{group.title}</p>
      )}
      {page.trails.length > 0 ? (
        <div className={styles.slots}>
          {page.trails.map((trail) => (
            <Slot key={trail.id} trail={trail} group={group} ctx={ctx} active={active} />
          ))}
        </div>
      ) : (
        <div className={styles.blankPage} aria-hidden="true">
          <svg viewBox="0 0 120 60">
            <path d="M6 54 38 18l14 16 20-24 42 44Z" />
          </svg>
        </div>
      )}
      <Folio page={index} />
    </div>
  );
}

function Medal({ milestone }: { milestone: Milestone }) {
  const r = 46;
  const circumference = 2 * Math.PI * r;
  const icons: Record<Milestone["id"], string> = {
    "first-hike": "M26 80 52 46l10 12 8-10 24 32M60 54V28l16 6-16 6",
    "first-overnight": "M30 76 60 34l30 42Zm30-42v42M74 30a8 8 0 1 1-8-10 6 6 0 0 0 8 10Z",
    "five-parks": "M26 76l16-26 10 14 12-22 20 34Z",
    "hundred-km": "M28 70c10-24 24-6 32-20s16-16 32-8",
  };
  return (
    <li className={`${styles.medal} ${milestone.earned ? styles.medalEarned : ""}`}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r="54" className={styles.medalBase} />
        {!milestone.earned && milestone.progress > 0 && (
          <circle
            cx="60"
            cy="60"
            r={r}
            className={styles.medalProgress}
            strokeDasharray={`${circumference * milestone.progress} ${circumference}`}
            transform="rotate(-90 60 60)"
          />
        )}
        <path d={icons[milestone.id]} className={styles.medalIcon} />
      </svg>
      <p className={styles.medalTitle}>{milestone.title}</p>
      <p className={styles.medalDetail}>
        {milestone.earned ? "Earned" : milestone.detail}
        <span className={styles.srOnly}>{milestone.earned ? `: ${milestone.detail}` : ", not earned yet"}</span>
      </p>
    </li>
  );
}

function Milestones({ ctx, index }: { ctx: PageContext; index: number }) {
  return (
    <div className={styles.paperInner}>
      <h2 className={styles.pageTitle}>Milestones</h2>
      <p className={styles.groupMeta}>
        {ctx.journal.milestones.filter((m) => m.earned).length} of {ctx.journal.milestones.length} earned
      </p>
      <ul className={styles.medals}>
        {ctx.journal.milestones.map((milestone) => (
          <Medal key={milestone.id} milestone={milestone} />
        ))}
      </ul>
      <p className={styles.footnote}>Distance counts trails with a known length.</p>
      <Folio page={index} />
    </div>
  );
}

function Back({ ctx }: { ctx: PageContext }) {
  return (
    <div className={`${styles.paperInner} ${styles.backPage}`}>
      <p className={styles.handwriting}>{ctx.guest ? "Your next adventure starts here." : "Where to next?"}</p>
      <Link href="/trail-list" className={styles.backLink}>
        Explore trails →
      </Link>
    </div>
  );
}

export function renderJournalPage(ctx: PageContext, index: number, active: boolean) {
  const page = ctx.journal.pages[index];
  switch (page.kind) {
    case "cover":
      return <Cover ctx={ctx} />;
    case "contents":
      return <Contents ctx={ctx} groups={page.groups} part={page.part} index={index} />;
    case "group":
      return <GroupPage ctx={ctx} page={page} index={index} active={active} />;
    case "milestones":
      return <Milestones ctx={ctx} index={index} />;
    case "back":
      return <Back ctx={ctx} />;
  }
}
