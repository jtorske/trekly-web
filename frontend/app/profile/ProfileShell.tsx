"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { CalendarDays, MapPin, Pencil, type LucideIcon } from "lucide-react";
import MilestoneBadge from "@/components/MilestoneBadge";
import TrailBadge from "@/components/TrailBadge";
import ui from "@/components/ui.module.css";
import { groupColour } from "@/lib/journal";
import type { Rank } from "@/lib/rank";
import { MAX_FEATURED, badgeKey, badgeName, type FeaturedBadge } from "@/lib/featuredBadges";
import styles from "./shell.module.css";

/** Below the fixed navbar (px), and the gap kept under a tall card. */
const STICKY_TOP = 104;
const STICKY_GAP = 16;

/**
 * The two-column profile layout shared by /profile (the owner) and
 * /u/[username] (read-only): a sticky identity card on the left and a tabbed
 * main pane. Below 900px the card becomes a compact header above the tabs.
 */
export function ProfileLayout({ banner, aside, children }: { banner?: ReactNode; aside: ReactNode; children: ReactNode }) {
  const asideRef = useRef<HTMLElement>(null);

  // A card taller than the window sticks by its bottom edge instead, so its
  // stats stay reachable: it scrolls with the page until its end is in view.
  useEffect(() => {
    const aside = asideRef.current;
    if (!aside) return;
    const place = () => {
      const top = Math.min(STICKY_TOP, window.innerHeight - aside.offsetHeight - STICKY_GAP);
      aside.style.setProperty("--sticky-top", `${top}px`);
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(aside);
    window.addEventListener("resize", place);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", place);
    };
  }, []);

  return (
    <main className={styles.page}>
      <div className={styles.wrap}>
        {banner}
        <div className={styles.columns}>
          <aside ref={asideRef} className={styles.aside}>
            {aside}
          </aside>
          <div className={styles.main}>{children}</div>
        </div>
      </div>
    </main>
  );
}

export interface StatRow {
  key: string;
  icon: LucideIcon;
  /** Singular and plural, e.g. ["Gear item", "Gear items"]. */
  label: [string, string];
  /** null while loading. */
  value: number | null;
  href?: string;
  onSelect?: () => void;
}

/** "Joined October 2026" from an ISO timestamp. */
export function joinedLabel(memberSince: string | null | undefined): string | null {
  if (!memberSince) return null;
  return `Joined ${new Date(memberSince).toLocaleDateString(undefined, { month: "long", year: "numeric" })}`;
}

export function IdentityCard({
  avatar,
  name,
  username,
  links,
  notice,
  bio,
  region,
  joined,
  rank,
  badges,
  action,
  stats,
  footer,
}: {
  avatar: ReactNode;
  name: string;
  username: string | null;
  /** "View public profile" and similar, under the username. */
  links?: ReactNode;
  /** Under the name, e.g. photo upload progress and errors. */
  notice?: ReactNode;
  bio?: string | null;
  region?: string | null;
  joined?: string | null;
  rank?: Rank | null;
  badges?: ReactNode;
  action?: ReactNode;
  stats: StatRow[];
  footer?: ReactNode;
}) {
  return (
    <div className={styles.card}>
      <div className={styles.identity}>
        <div className={styles.avatarSlot}>{avatar}</div>
        <div className={styles.identityText}>
          <h1 className={styles.name}>{name}</h1>
          {username && <p className={styles.username}>@{username}</p>}
          {links && <div className={styles.links}>{links}</div>}
        </div>
      </div>

      {notice}

      {bio && <p className={styles.bio}>{bio}</p>}

      {(region || joined) && (
        <ul className={styles.meta}>
          {region && (
            <li>
              <MapPin size={16} aria-hidden="true" />
              {region}
            </li>
          )}
          {joined && (
            <li>
              <CalendarDays size={16} aria-hidden="true" />
              {joined}
            </li>
          )}
        </ul>
      )}

      {rank && (
        <p className={styles.rank}>
          <span className={styles.rankLevel} aria-hidden="true">
            {rank.level}
          </span>
          <span>
            <span className={ui.srOnly}>Rank {rank.level}: </span>
            {rank.title}
          </span>
        </p>
      )}

      {badges}

      {action && <div className={styles.action}>{action}</div>}

      {stats.length > 0 && (
        <>
          <hr className={styles.divider} />
          <ul className={styles.stats} aria-label="Stats">
            {stats.map((stat) => (
              <li key={stat.key}>
                <StatLink stat={stat} />
              </li>
            ))}
          </ul>
        </>
      )}

      {footer && <div className={styles.footer}>{footer}</div>}
    </div>
  );
}

function StatLink({ stat }: { stat: StatRow }) {
  const Icon = stat.icon;
  const label = stat.value === 1 ? stat.label[0] : stat.label[1];
  const content = (
    <>
      <Icon className={styles.statIcon} size={18} aria-hidden="true" />
      <span className={styles.statLabel}>{label}</span>
      {stat.value === null ? (
        <span className={`${ui.skeleton} ${styles.statSkeleton}`} aria-label="Loading" />
      ) : (
        <span className={styles.statValue}>{stat.value}</span>
      )}
    </>
  );
  if (stat.href) {
    return (
      <Link href={stat.href} className={styles.stat}>
        {content}
      </Link>
    );
  }
  return (
    <button type="button" className={styles.stat} onClick={stat.onSelect} disabled={!stat.onSelect}>
      {content}
    </button>
  );
}

/** A featured badge's art: the trail's Trail Journal badge, or a milestone medal. */
export function BadgeArt({ badge, className }: { badge: FeaturedBadge; className?: string }) {
  if (badge.kind === "milestone") return <MilestoneBadge id={badge.milestone} title={badgeName(badge)} className={className} />;
  const { trail } = badge;
  return <TrailBadge name={trail.name} terrain={trail.terrain} colour={groupColour(`region:${trail.region}`)} hiked className={className} />;
}

/**
 * The identity card's three featured badge slots. A trail badge opens its
 * trail; the name shows on hover and focus. Owners also see empty slots,
 * the Edit button and, with no badges yet, how to earn one; visitors see
 * only filled slots, and nothing at all without any.
 */
export function FeaturedBadgeSlots({
  badges,
  loading = false,
  onEdit,
}: {
  badges: FeaturedBadge[];
  loading?: boolean;
  /** Present for the owner. */
  onEdit?: () => void;
}) {
  const owner = Boolean(onEdit);
  if (!owner && badges.length === 0) return null;
  const slots = owner ? MAX_FEATURED : badges.length;
  return (
    <div>
      <div className={styles.badgesHead}>
        <p className={styles.badgesLabel} id="featured-badges">
          Featured badges
        </p>
        {onEdit && (badges.length > 0 || loading) && (
          <button type="button" className={styles.badgesEdit} onClick={onEdit} disabled={loading}>
            <Pencil size={14} aria-hidden="true" />
            Edit<span className={ui.srOnly}> featured badges</span>
          </button>
        )}
      </div>
      <ul className={styles.badges} aria-labelledby="featured-badges" aria-busy={loading || undefined}>
        {Array.from({ length: slots }, (_, index) => {
          const badge = badges[index];
          if (loading) return <li key={index} className={`${ui.skeleton} ${styles.badgeSkeleton}`} aria-hidden="true" />;
          if (!badge) return <li key={index} className={styles.badgeEmpty} aria-label="Empty badge slot" />;
          const name = badgeName(badge);
          const art = <BadgeArt badge={badge} className={styles.badge} />;
          return (
            <li key={badgeKey(badge)} className={styles.badgeSlot}>
              {badge.kind === "trail" ? (
                <Link href={`/trails?id=${encodeURIComponent(badge.trail.id)}`} className={styles.badgeLink} aria-label={`${name}: open the trail`}>
                  {art}
                </Link>
              ) : (
                <span className={styles.badgeLink} tabIndex={0}>
                  {art}
                </span>
              )}
              <span className={styles.badgeTip} aria-hidden="true">
                {name}
              </span>
            </li>
          );
        })}
      </ul>
      {owner && !loading && badges.length === 0 && (
        <p className={styles.badgesHint}>
          <Link href="/trail-list">Hike a trail to earn your first badge</Link>
        </p>
      )}
    </div>
  );
}

export interface TabItem<K extends string> {
  key: K;
  label: string;
  /** Shown beside the label; null while loading, undefined for none. */
  count?: number | null;
}

/**
 * WAI-ARIA tabs (arrows, Home and End move and select). The underline is one
 * element that slides to the selected tab; when the tabs overflow (on a phone)
 * the bar scrolls sideways and fades at an edge with more tabs past it.
 */
export function ProfileTabs<K extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: TabItem<K>[];
  active: K;
  onChange: (key: K) => void;
  label: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ x: number; width: number } | null>(null);
  const [fade, setFade] = useState({ start: false, end: false });

  const measure = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    const tab = list.querySelector<HTMLElement>('[aria-selected="true"]');
    if (tab) setIndicator({ x: tab.offsetLeft, width: tab.offsetWidth });
    setFade({
      start: list.scrollLeft > 1,
      end: list.scrollLeft + list.clientWidth < list.scrollWidth - 1,
    });
  }, []);

  useLayoutEffect(measure, [measure, active, tabs]);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    // Web fonts change the tab widths once they load.
    document.fonts?.ready.then(measure).catch(() => undefined);
    return () => observer.disconnect();
  }, [measure]);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[aria-selected="true"]')
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active]);

  const select = (index: number) => {
    const next = tabs[(index + tabs.length) % tabs.length];
    onChange(next.key);
    document.getElementById(`tab-${next.key}`)?.focus();
  };

  return (
    <div className={styles.tabBar} data-fade-start={fade.start || undefined} data-fade-end={fade.end || undefined}>
      <div ref={listRef} className={styles.tabs} role="tablist" aria-label={label} onScroll={measure}>
        {tabs.map((item, index) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            id={`tab-${item.key}`}
            aria-selected={active === item.key}
            aria-controls={`panel-${item.key}`}
            tabIndex={active === item.key ? 0 : -1}
            className={styles.tab}
            onClick={() => onChange(item.key)}
            onKeyDown={(event) => {
              const moves: Record<string, number> = {
                ArrowRight: index + 1,
                ArrowLeft: index - 1,
                Home: 0,
                End: tabs.length - 1,
              };
              if (event.key in moves) {
                event.preventDefault();
                select(moves[event.key]);
              }
            }}
          >
            {item.label}
            {item.count === null ? (
              <span className={`${ui.skeleton} ${styles.tabCountSkeleton}`} aria-hidden="true" />
            ) : (
              item.count !== undefined && <span className={styles.tabCount}>{item.count}</span>
            )}
          </button>
        ))}
        {indicator && (
          <span
            className={styles.indicator}
            style={{ transform: `translateX(${indicator.x}px)`, width: indicator.width }}
            aria-hidden="true"
          />
        )}
      </div>
    </div>
  );
}

/** A titled card in the main pane, with an optional right-aligned link. */
export function SectionCard({
  id,
  title,
  count,
  action,
  children,
}: {
  id?: string;
  title: string;
  count?: number;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={styles.section} aria-labelledby={id ? `${id}-title` : undefined}>
      <div className={styles.sectionHead}>
        <h2 id={id ? `${id}-title` : undefined} className={styles.sectionTitle}>
          {title}
          {count != null && <span className={styles.sectionCount}>{count}</span>}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** The whole page while the profile itself loads, laid out like the real one. */
export function ProfileSkeleton() {
  return (
    <main className={styles.page} aria-busy="true" aria-label="Loading profile">
      <div className={styles.wrap}>
        <div className={styles.columns}>
          <aside className={styles.aside}>
            <div className={styles.card}>
              <div className={styles.identity}>
                <div className={`${ui.skeleton} ${styles.skeletonAvatar}`} />
                <div className={styles.identityText}>
                  <div className={`${ui.skeleton} ${styles.skeletonName}`} />
                  <div className={`${ui.skeleton} ${styles.skeletonShort}`} />
                </div>
              </div>
              <div className={`${ui.skeleton} ${styles.skeletonButton}`} />
              <hr className={styles.divider} />
              <div className={styles.stats}>
                {[0, 1, 2, 3].map((row) => (
                  <div key={row} className={`${ui.skeleton} ${styles.skeletonStat}`} />
                ))}
              </div>
            </div>
          </aside>
          <div className={styles.main}>
            <div className={`${ui.skeleton} ${styles.skeletonTabs}`} />
            <div className={`${ui.skeleton} ${styles.skeletonSection}`} />
            <div className={`${ui.skeleton} ${styles.skeletonSection}`} />
          </div>
        </div>
      </div>
    </main>
  );
}
