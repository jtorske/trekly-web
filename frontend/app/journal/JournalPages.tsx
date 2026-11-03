"use client";

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import MilestoneBadge from "@/components/MilestoneBadge";
import RankEmblem from "@/components/RankEmblem";
import TrailBadge from "@/components/TrailBadge";
import type { HikeLog } from "@/lib/hikeLogsApi";
import { BADGE_COLOURS, badgeGrid, halves, hikedInGroup, type Journal, type JournalGroup, type JournalSection } from "@/lib/journal";
import {
  earnedCount,
  milestoneDetail,
  MEDALS_PER_PAGE,
  milestoneKey,
  progressFraction,
  progressLabel,
  TIER_NAMES,
  type Milestone,
  type MilestonePage,
  type Milestones,
  type Tier,
} from "@/lib/milestones";
import type { UnitSystem } from "@/lib/units";
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
  units: UnitSystem;
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

type ContentsEntry = { slug: string; title: string; colour: string; done: number; total: number; noun: string };

function contentsEntries(ctx: PageContext): ContentsEntry[] {
  return ctx.journal.sections.flatMap((section): ContentsEntry[] => {
    if (section.kind === "group") {
      const { group } = section;
      return [{ slug: section.slug, title: group.title, colour: group.colour, done: hikedIn(group, ctx.logs), total: group.trails.length, noun: "hiked" }];
    }
    // One entry for all the milestone spreads: the overview, which links on to each category.
    if (section.kind === "milestones" && section.first && ctx.journal.milestones) {
      const all = ctx.journal.milestones;
      return [{ slug: section.slug, title: "Milestones", colour: "var(--color-tan)", done: earnedCount(all), total: all.milestones.length, noun: "earned" }];
    }
    return [];
  });
}

/** A small inked check, stamped beside a finished section. */
function DoneStamp({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="m7.5 12.5 3 3 6-7" />
    </svg>
  );
}

/** The owner's rank on the opening page (the journal is only ever its owner's). */
function JournalRank() {
  const { rank } = useRank();
  if (!rank) return null;
  return (
    <span className={styles.rankChip}>
      <RankEmblem level={rank.rank.level} className={styles.rankChipEmblem} />
      <span className={styles.srOnly}>Rank: </span>
      <span className={styles.rankChipTitle}>{rank.rank.title}</span>
    </span>
  );
}

function Contents({
  ctx,
  entries,
  rows,
  first,
  last,
}: {
  ctx: PageContext;
  entries: ContentsEntry[];
  /** Row slots on the page; both pages of a spread share one count, so their rows line up. */
  rows: number;
  first: boolean;
  last: boolean;
}) {
  const { journal, owner } = ctx;
  // From every entry, not just this page's, so the column matches across the spread.
  const countWidth = Math.max(...contentsEntries(ctx).map((entry) => `${entry.done}/${entry.total}`.length));
  return (
    <div className={`${styles.paperInner} ${styles.contentsPage}`}>
      {/* Both pages' headers and footers have fixed, equal heights, so the rows between them match across the spread. */}
      <header className={styles.contentsHeader}>
        {first ? (
          <>
            <PageTitle>Contents</PageTitle>
            <p className={styles.contentsOwner}>{owner && <>{owner}&apos;s journal</>}</p>
            <div className={styles.contentsProgress}>
              <span className={styles.progressBar} aria-hidden="true">
                <span style={{ width: `${journal.total ? (journal.hiked / journal.total) * 100 : 0}%` }} />
              </span>
              <span className={styles.progressText}>
                {journal.hiked} / {journal.total} trails hiked
              </span>
              <JournalRank />
            </div>
          </>
        ) : (
          <p className={`${styles.pageTitle} ${styles.contentsContinued}`}>Contents, continued</p>
        )}
      </header>
      <ol className={styles.contents} style={{ "--rows": Math.max(rows, 1), "--count-ch": countWidth } as CSSProperties}>
        {entries.map((entry) => {
          const started = entry.done > 0;
          const complete = entry.total > 0 && entry.done >= entry.total;
          return (
            <li key={entry.slug}>
              <button
                type="button"
                className={`${styles.contentsRow} ${started ? styles.contentsStarted : ""}`}
                onClick={() => ctx.onOpen(entry.slug)}
              >
                <span className={styles.contentsDot} style={{ background: entry.colour }} aria-hidden="true" />
                <span className={styles.contentsName}>{entry.title}</span>
                {complete && <DoneStamp className={styles.contentsStamp} />}
                <span className={styles.contentsLeader} aria-hidden="true" />
                <span className={styles.contentsCount}>
                  {entry.done}/{entry.total}
                  <span className={styles.srOnly}>
                    {" "}
                    {entry.noun}
                    {complete && ", complete"}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {last ? (
        <div className={styles.contentsFoot}>
          <p className={styles.legendTitle}>Badge shapes</p>
          <ul>
            {(["easy", "moderate", "difficult", "extreme"] as const).map((terrain) => (
              <li key={terrain}>
                <span className={styles.footSample}>
                  <TrailBadge name="" terrain={terrain} colour={BADGE_COLOURS[0]} hiked className={styles.legendBadge} />
                </span>
                <span>{terrain[0].toUpperCase() + terrain.slice(1)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className={styles.contentsFoot} aria-hidden="true">
          <p className={styles.legendTitle}>Reading the contents</p>
          <ul>
            <li>
              <span className={styles.footSample}>
                <span className={styles.keyCount}>0/4</span>
              </span>
              <span>Not started</span>
            </li>
            <li>
              <span className={`${styles.footSample} ${styles.contentsStarted}`}>
                <span className={styles.keyCount}>1/4</span>
              </span>
              <span>Under way</span>
            </li>
            <li>
              <span className={`${styles.footSample} ${styles.contentsStarted}`}>
                <DoneStamp className={styles.keyStamp} />
                <span className={styles.keyCount}>4/4</span>
              </span>
              <span>Complete</span>
            </li>
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

/** Small print under a category, where its rules need saying. */
const CATEGORY_NOTES: Record<string, string> = {
  nights: "A trip's nights are its trail's typical nights.",
  distance: "Counts trails with a known length.",
  elevation: "Counts trails with known elevation.",
  routes: "Counts trails with a known route type.",
  seasons: "A trip counts on every day from its hike date through its nights.",
};

function Medal({ ctx, milestone, index, active }: { ctx: PageContext; milestone: Milestone; index: number; active: boolean }) {
  const stampKey = `milestone:${milestone.id}`;
  const stamp = active && milestone.earned && !ctx.stamped.has(stampKey);
  const progress = progressLabel(milestone, ctx.units);
  const detail = milestoneDetail(milestone, ctx.units);
  const tier = milestone.tier ? TIER_NAMES[milestone.tier] : null;
  return (
    <li className={styles.medal} data-key={milestoneKey(milestone, index)}>
      <span className={styles.medalBox}>
        <MilestoneBadge
          icon={milestone.icon}
          tier={milestone.tier}
          earned={milestone.earned}
          progress={progressFraction(milestone)}
          stamp={stamp}
          onStamped={() => ctx.onStamped(stampKey)}
          className={styles.medalArt}
        />
      </span>
      <p className={styles.medalTitle}>
        {milestone.title}
        {milestone.secret && !milestone.earned && <span className={styles.srOnly}> (secret milestone)</span>}
      </p>
      <p className={styles.medalDetail}>
        {milestone.earned ? (
          <>
            <span className={styles.medalTier} data-tier={milestone.tier ?? undefined}>
              {tier}
            </span>
            {" · "}Earned
            <span className={styles.srOnly}>: {detail}</span>
          </>
        ) : (
          <>
            {detail}
            {milestone.needs_data ? (
              <>
                {" · "}
                <span className={styles.medalWaiting}>Needs more trail data</span>
              </>
            ) : (
              progress && <span className={styles.medalProgress}> ({progress})</span>
            )}
            <span className={styles.srOnly}>{tier ? `, ${tier.toLowerCase()} tier` : ""}, not earned yet</span>
          </>
        )}
      </p>
    </li>
  );
}

/** Columns and rows for a category's medals (at most two across, so names have room). */
function medalGrid(count: number) {
  const columns = count <= 1 ? 1 : 2;
  return { "--columns": columns, "--rows": Math.max(1, Math.ceil(count / columns)) } as CSSProperties;
}

function CategoryPage({
  ctx,
  page,
  back,
  active,
}: {
  ctx: PageContext;
  page: Extract<MilestonePage, { kind: "category" }>;
  back: boolean;
  active: boolean;
}) {
  // The count is the whole category's, on a continued page too.
  const all = ctx.journal.milestones?.milestones.filter((m) => m.category === page.category.id) ?? page.milestones;
  const earned = all.filter((m) => m.earned).length;
  const note = CATEGORY_NOTES[page.category.id];
  return (
    <div className={styles.paperInner}>
      {back && <BackToContents ctx={ctx} />}
      <header className={`${styles.groupHeader} ${styles.milestoneHeader}`}>
        <p className={styles.runningHead}>{page.continued ? "Milestones, continued" : "Milestones"}</p>
        <PageTitle>{page.category.title}</PageTitle>
        <p className={styles.groupMeta}>
          {earned} of {all.length} earned
        </p>
      </header>
      {/* A continued page keeps its first page's rows, so the medals stay one size. */}
      <ul className={styles.medals} style={medalGrid(page.continued ? MEDALS_PER_PAGE : page.milestones.length)}>
        {page.milestones.map((milestone, index) => (
          <Medal key={milestoneKey(milestone, index)} ctx={ctx} milestone={milestone} index={index} active={active} />
        ))}
      </ul>
      {note && <p className={styles.footnote}>{note}</p>}
    </div>
  );
}

/** "3 of 14" earned in a tier (hidden secrets have no tier, so they're not counted). */
function tierCounts(data: Milestones, tier: Tier) {
  const all = data.milestones.filter((m) => m.tier === tier);
  return `${all.filter((m) => m.earned).length} of ${all.length}`;
}

/** The first milestones page: the overall count, the tiers, and a link to each category. */
function Overview({ ctx, sections }: { ctx: PageContext; sections: Extract<JournalSection, { kind: "milestones" }>[] }) {
  const data = ctx.journal.milestones;
  if (!data) return null;
  const slugOf = (categoryId: string) =>
    sections.find((section) =>
      [section.spread.left, section.spread.right].some((page) => page.kind === "category" && page.category.id === categoryId),
    )?.slug;
  return (
    <div className={styles.paperInner}>
      <BackToContents ctx={ctx} />
      <header className={`${styles.groupHeader} ${styles.milestoneHeader}`}>
        <span className={styles.tape} style={{ background: "var(--color-tan)" }} aria-hidden="true" />
        <PageTitle>Milestones</PageTitle>
        <p className={styles.groupMeta}>
          {earnedCount(data)} of {data.milestones.length} earned
        </p>
      </header>
      <ul className={styles.tiers} aria-label="Tiers">
        {(["bronze", "silver", "gold"] as const).map((tier) => (
          <li key={tier}>
            <MilestoneBadge icon="first-hike" tier={tier} className={styles.tierBadge} />
            <span className={styles.tierName}>{TIER_NAMES[tier]}</span>
            <span className={styles.tierMeta}>
              +{data.tier_points[tier]} pts · {tierCounts(data, tier)}
            </span>
          </li>
        ))}
      </ul>
      <ol className={`${styles.contents} ${styles.categoryList}`} style={{ "--rows": data.categories.length, "--count-ch": 5 } as CSSProperties}>
        {data.categories.map((category) => {
          const inCategory = data.milestones.filter((m) => m.category === category.id);
          const slug = slugOf(category.id);
          return (
            <li key={category.id}>
              <button type="button" className={styles.contentsRow} onClick={() => slug && ctx.onOpen(slug)}>
                <span className={styles.contentsName}>{category.title}</span>
                <span className={styles.contentsLeader} aria-hidden="true" />
                <span className={styles.contentsCount}>
                  {inCategory.filter((m) => m.earned).length}/{inCategory.length}
                  <span className={styles.srOnly}> earned</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function BlankPage() {
  return (
    <div className={styles.paperInner}>
      <div className={styles.blankPage} aria-hidden="true">
        <svg viewBox="0 0 120 60">
          <path d="M6 54 38 18l14 16 20-24 42 44Z" />
        </svg>
      </div>
    </div>
  );
}

function MilestonePageView({ ctx, page, back, active }: { ctx: PageContext; page: MilestonePage; back: boolean; active: boolean }) {
  switch (page.kind) {
    case "overview": {
      const sections = ctx.journal.sections.filter((s): s is Extract<JournalSection, { kind: "milestones" }> => s.kind === "milestones");
      return <Overview ctx={ctx} sections={sections} />;
    }
    case "category":
      return <CategoryPage ctx={ctx} page={page} back={back} active={active} />;
    case "blank":
      return <BlankPage />;
    case "back":
      return <Back />;
  }
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
function SinglePage({ all, first, second }: { all: ReactNode | null; first: ReactNode; second: ReactNode }) {
  // Without an `all`, always one half at a time.
  const whole = all === null ? 0 : "all";
  const [part, setPart] = useState<"all" | 0 | 1>(whole);
  const box = useRef<HTMLDivElement>(null);
  const turned = useRef(false);

  useLayoutEffect(() => {
    const el = box.current;
    // Measured after layout and before paint, so the overflowing version never shows.
    if (part === "all" && el && el.scrollHeight > el.clientHeight + 1) setPart(0);
  }, [part]);

  // A new page size might fit the whole section after all (or no longer).
  useEffect(() => {
    // The page's sheet, not the box: the box remounts on every turn, and a
    // detached box shrinking to 0×0 would read as a resize and turn back.
    const el = box.current?.parentElement;
    if (!el) return;
    let size = `${el.clientWidth}x${el.clientHeight}`;
    const observer = new ResizeObserver(() => {
      const next = `${el.clientWidth}x${el.clientHeight}`;
      if (next === size) return;
      size = next;
      turned.current = false;
      setPart(whole);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [whole]);

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
      // halves puts any extra entry on the left, so it sets the row count for both pages.
      const rows = left.length;
      if (view === "left") return <Contents ctx={ctx} entries={left} rows={rows} first last={false} />;
      if (view === "right") return <Contents ctx={ctx} entries={right} rows={rows} first={false} last />;
      return (
        <SinglePage
          all={<Contents ctx={ctx} entries={entries} rows={entries.length} first last />}
          first={<Contents ctx={ctx} entries={left} rows={rows} first last={false} />}
          second={<Contents ctx={ctx} entries={right} rows={rows} first={false} last />}
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
    case "milestones": {
      const { left, right } = section.spread;
      if (view === "left") return <MilestonePageView ctx={ctx} page={left} back active={active} />;
      if (view === "right") return <MilestonePageView ctx={ctx} page={right} back={false} active={active} />;
      return (
        <SinglePage
          all={null}
          first={<MilestonePageView ctx={ctx} page={left} back active={active} />}
          second={<MilestonePageView ctx={ctx} page={right} back active={active} />}
        />
      );
    }
  }
}

export function renderJournalPage(ctx: PageContext, index: number, view: View, active: boolean) {
  return renderSection(ctx, ctx.journal.sections[index], view, active);
}
