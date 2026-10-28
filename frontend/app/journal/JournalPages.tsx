"use client";

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import RankEmblem from "@/components/RankEmblem";
import TrailBadge from "@/components/TrailBadge";
import { MILESTONE_ICONS } from "@/lib/badge";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { BADGE_COLOURS, badgeGrid, halves, hikedInGroup, type Journal, type JournalGroup, type JournalSection, type Milestone } from "@/lib/journal";
import { useHikePhoto } from "@/lib/useHikePhoto";
import { useRank } from "@/lib/useRank";
import type { TrailListItem } from "@/lib/trailsApi";
import type { View } from "./Book";
import styles from "./journal.module.css";

export const formatHikeDate = (iso: string, month: "short" | "long" = "short") =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month, day: "numeric", year: "numeric" });

export interface PageContext {
  journal: Journal;
  logs: Map<string, HikeLog>;
  owner: string | null;
  stamped: Set<string>;
  onStamped: (trailId: string) => void;
  onOpenEntry: (log: HikeLog, colour: string) => void;
  /** Open a section by its slug (null is the contents). */
  onOpen: (slug: string | null) => void;
}

/** The closed book a signed-out visitor sees. */
export function GuestCover() {
  return (
    <div className={styles.cover}>
      <div className={styles.coverFrame}>
        <p className={styles.coverEyebrow}>Trekly</p>
        <p className={styles.coverTitle} aria-hidden="true">
          Trail Journal
        </p>
        <svg viewBox="0 0 120 40" className={styles.coverMark} aria-hidden="true">
          <path d="M4 36 34 10l12 12 18-18 26 24 10-8 16 16Z" />
        </svg>
        <div className={styles.coverGuest}>
          <p>Every trail you hike earns a stamp in this book.</p>
          <Link href="/login?next=%2Fjournal" className={styles.coverButton}>
            Sign in to start your journal
          </Link>
          <p className={styles.coverSmall}>
            New to Trekly? <Link href="/signup?next=%2Fjournal">Create an account</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

function BackToContents({ ctx }: { ctx: PageContext }) {
  return (
    <button type="button" className={styles.toContents} onClick={() => ctx.onOpen(null)}>
      <span aria-hidden="true">←</span> Back to contents
    </button>
  );
}

/** A page's title; Book focuses it once the page turns into view. */
function PageTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className={styles.pageTitle} tabIndex={-1} data-page-title>
      {children}
    </h2>
  );
}

const hikedIn = (group: JournalGroup, logs: Map<string, HikeLog>) => hikedInGroup(group, logs);

type ContentsEntry = { slug: string; title: string; colour: string; count: string; noun: string };

function contentsEntries(ctx: PageContext): ContentsEntry[] {
  return ctx.journal.sections.flatMap((section): ContentsEntry[] => {
    if (section.kind === "group") {
      const { group } = section;
      return [{ slug: section.slug, title: group.title, colour: group.colour, count: `${hikedIn(group, ctx.logs)}/${group.trails.length}`, noun: "hiked" }];
    }
    if (section.kind === "milestones") {
      const earned = ctx.journal.milestones.filter((m) => m.earned).length;
      return [{ slug: section.slug, title: section.title, colour: "var(--color-tan)", count: `${earned}/${ctx.journal.milestones.length}`, noun: "earned" }];
    }
    return [];
  });
}

/** The owner's rank on the opening page (the journal is only ever its owner's). */
function JournalRank() {
  const { rank } = useRank();
  if (!rank) return null;
  return (
    <span className={styles.contentsRank}>
      {" · "}
      <RankEmblem level={rank.rank.level} className={styles.contentsRankEmblem} />
      <span className={styles.srOnly}>Rank: </span>
      {rank.rank.title}
    </span>
  );
}

function Contents({ ctx, entries, first, last }: { ctx: PageContext; entries: ContentsEntry[]; first: boolean; last: boolean }) {
  const { journal, owner } = ctx;
  return (
    <div className={styles.paperInner}>
      {first ? (
        <header className={styles.contentsHeader}>
          <PageTitle>Contents</PageTitle>
          <p className={styles.groupMeta}>
            {owner && <span className={styles.contentsOwner}>{owner}&apos;s journal · </span>}
            {journal.hiked} of {journal.total} trails hiked
            <JournalRank />
          </p>
        </header>
      ) : (
        <header className={styles.contentsHeader}>
          <p className={styles.runningHead}>Contents, continued</p>
        </header>
      )}
      <ol className={styles.contents}>
        {entries.map((entry) => (
          <li key={entry.slug}>
            <button type="button" className={styles.contentsRow} onClick={() => ctx.onOpen(entry.slug)}>
              <span className={styles.contentsDot} style={{ background: entry.colour }} aria-hidden="true" />
              <span className={styles.contentsName}>{entry.title}</span>
              <span className={styles.contentsLeader} aria-hidden="true" />
              <span className={styles.contentsCount}>
                {entry.count}
                <span className={styles.srOnly}> {entry.noun}</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      {last && (
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
        <span className={styles.badgeBox}>
          <TrailBadge name={trail.name} terrain={trail.terrain} colour={group.colour} hiked={false} className={styles.badge} />
        </span>
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
      <span className={styles.badgeBox}>
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
      </span>
      <span className={`${styles.slotCaption} ${styles.slotDate}`}>{formatHikeDate(log.hiked_on)}</span>
    </button>
  );
}

function GroupPage({
  ctx,
  group,
  trails,
  head,
  back,
  grid,
  readable = false,
  active,
}: {
  ctx: PageContext;
  group: JournalGroup;
  trails: TrailListItem[];
  /** The opening page carries the title; the facing page only a running head. */
  head: boolean;
  /** Back to contents; defaults to `head`. A phone's second page stands alone, so it needs one too. */
  back?: boolean;
  grid: { columns: number; rows: number };
  /** Keep badges at a readable size even if the page overflows (a phone then splits it). */
  readable?: boolean;
  active: boolean;
}) {
  return (
    <div className={styles.paperInner}>
      {(back ?? head) && <BackToContents ctx={ctx} />}
      <header className={styles.groupHeader}>
        {head ? (
          <>
            <span className={styles.tape} style={{ background: group.colour }} aria-hidden="true" />
            <PageTitle>{group.title}</PageTitle>
            <p className={styles.groupMeta}>
              {group.subtitle && <span>{group.subtitle} · </span>}
              {hikedIn(group, ctx.logs)} of {group.trails.length} hiked
            </p>
          </>
        ) : (
          <p className={styles.runningHead}>{group.title}</p>
        )}
      </header>
      {trails.length > 0 ? (
        <div
          className={`${styles.slots} ${readable ? styles.slotsReadable : ""}`}
          style={{ "--columns": grid.columns, "--rows": grid.rows } as CSSProperties}
        >
          {trails.map((trail) => (
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
    </div>
  );
}

function Medal({ milestone }: { milestone: Milestone }) {
  const r = 46;
  const circumference = 2 * Math.PI * r;
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
        <path d={MILESTONE_ICONS[milestone.id]} className={styles.medalIcon} />
      </svg>
      <p className={styles.medalTitle}>{milestone.title}</p>
      <p className={styles.medalDetail}>
        {milestone.earned ? "Earned" : milestone.detail}
        <span className={styles.srOnly}>{milestone.earned ? `: ${milestone.detail}` : ", not earned yet"}</span>
      </p>
    </li>
  );
}

function Milestones({ ctx }: { ctx: PageContext }) {
  return (
    <div className={styles.paperInner}>
      <BackToContents ctx={ctx} />
      <header className={styles.groupHeader}>
        <PageTitle>Milestones</PageTitle>
        <p className={styles.groupMeta}>
          {ctx.journal.milestones.filter((m) => m.earned).length} of {ctx.journal.milestones.length} earned
        </p>
      </header>
      <ul className={styles.medals}>
        {ctx.journal.milestones.map((milestone) => (
          <Medal key={milestone.id} milestone={milestone} />
        ))}
      </ul>
      <p className={styles.footnote}>Distance counts trails with a known length.</p>
    </div>
  );
}

function Back() {
  return (
    <div className={`${styles.paperInner} ${styles.backPage}`}>
      <p className={styles.handwriting}>Where to next?</p>
      <Link href="/trail-list" className={styles.backLink}>
        Explore trails →
      </Link>
    </div>
  );
}

/**
 * A phone's page. It shows the whole section if that fits; otherwise the
 * section's two desktop pages, one at a time, with a small link between
 * them. Fit is measured, so it holds at any screen height.
 */
function SinglePage({ all, first, second }: { all: ReactNode; first: ReactNode; second: ReactNode }) {
  const [part, setPart] = useState<"all" | 0 | 1>("all");
  const box = useRef<HTMLDivElement>(null);
  const turned = useRef(false);

  useLayoutEffect(() => {
    const el = box.current;
    // Measured after layout and before paint, so the overflowing version never shows.
    if (part === "all" && el && el.scrollHeight > el.clientHeight + 1) setPart(0);
  }, [part]);

  // A new page size might fit the whole section after all (or no longer).
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let size = `${el.clientWidth}x${el.clientHeight}`;
    const observer = new ResizeObserver(() => {
      const next = `${el.clientWidth}x${el.clientHeight}`;
      if (next === size) return;
      size = next;
      turned.current = false;
      setPart("all");
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Keep focus on the link between the two pages as it moves.
  useEffect(() => {
    if (!turned.current || part === "all") return;
    box.current?.parentElement?.querySelector<HTMLElement>("[data-page-turn]")?.focus({ preventScroll: true });
  }, [part]);

  const turn = (to: 0 | 1) => {
    turned.current = true;
    setPart(to);
  };

  return (
    <>
      <div ref={box} className={styles.fit} key={part} data-part={part}>
        {part === "all" ? all : part === 0 ? first : second}
      </div>
      {part === 0 && (
        <button type="button" className={`${styles.pageTurn} ${styles.pageTurnNext}`} onClick={() => turn(1)} data-page-turn>
          More <span aria-hidden="true">→</span>
        </button>
      )}
      {part === 1 && (
        <button type="button" className={`${styles.pageTurn} ${styles.pageTurnPrev}`} onClick={() => turn(0)} data-page-turn>
          <span aria-hidden="true">←</span> Previous
        </button>
      )}
    </>
  );
}

function renderSection(ctx: PageContext, section: JournalSection, view: View, active: boolean) {
  switch (section.kind) {
    case "contents": {
      const entries = contentsEntries(ctx);
      const [left, right] = halves(entries);
      if (view === "left") return <Contents ctx={ctx} entries={left} first last={false} />;
      if (view === "right") return <Contents ctx={ctx} entries={right} first={false} last />;
      return (
        <SinglePage
          all={<Contents ctx={ctx} entries={entries} first last />}
          first={<Contents ctx={ctx} entries={left} first last={false} />}
          second={<Contents ctx={ctx} entries={right} first={false} last />}
        />
      );
    }
    case "group": {
      const { group } = section;
      const [left, right] = halves(group.trails);
      // Both pages of a spread share one grid, so badges match across the gutter.
      const grid = badgeGrid(left.length);
      const page = (trails: TrailListItem[], head: boolean, back = head) => (
        <GroupPage ctx={ctx} group={group} trails={trails} head={head} back={back} grid={grid} active={active} />
      );
      if (view === "left") return page(left, true);
      if (view === "right") return page(right, false);
      return (
        <SinglePage
          all={<GroupPage ctx={ctx} group={group} trails={group.trails} head grid={badgeGrid(group.trails.length)} readable active={active} />}
          first={page(left, true)}
          second={page(right, false, true)}
        />
      );
    }
    case "milestones":
      return view === "right" ? <Back /> : <Milestones ctx={ctx} />;
  }
}

export function renderJournalPage(ctx: PageContext, index: number, view: View, active: boolean) {
  return renderSection(ctx, ctx.journal.sections[index], view, active);
}
