"use client";

import AccountBadge from "@/components/AccountBadge";
import type { AccountLabel } from "@/lib/accountLabels";
import { Activity, createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { CalendarDays, MapPin, Pencil } from "lucide-react";
import MilestoneBadge from "@/components/MilestoneBadge";
import MilestoneBadgeCard from "@/components/MilestoneBadgeCard";
import { BadgeCardBody, CardLine, DetailCard } from "@/components/MilestoneCard";
import ProvinceBadge from "@/components/ProvinceBadge";
import RankEmblem from "@/components/RankEmblem";
import StreakFlame from "@/components/StreakFlame";
import TrailBadge from "@/components/TrailBadge";
import ui from "@/components/ui.module.css";
import { groupColour } from "@/lib/journal";
import { homeLabel, province as findProvince, type Province } from "@/lib/provinces";
import { trailBadgeHiked } from "@/lib/publicProfile";
import { TERRAIN_LABELS } from "@/lib/terrain";
import type { TrailListItem } from "@/lib/trailsApi";
import type { Rank } from "@/lib/rank";
import { bestLabel, showsStreak, streakLabel, type StreakCounts } from "@/lib/visitStreak";
import { MAX_FEATURED, badgeKey, badgeName, type FeaturedBadge } from "@/lib/featuredBadges";
import { useQueryParam } from "@/lib/useQueryParam";
import styles from "./shell.module.css";
import { trailHref } from "@/lib/site";

/** Which tabs this profile has, and the one open when ?tab= names none of them. */
export interface ProfileTabConfig {
  keys: string[];
  fallback: string;
}

const TabConfigContext = createContext<ProfileTabConfig | null>(null);

/**
 * The open tab, from ?tab= in the URL. Only the tab bar and the panels read
 * it, so a click repaints those and not the page (which would
 * hand every hidden panel new props to render before it could show).
 */
function useOpenTab(): string | null {
  const config = useContext(TabConfigContext);
  const requested = useQueryParam("tab");
  if (!config) return null;
  return requested !== null && config.keys.includes(requested) ? requested : config.fallback;
}

/**
 * The two-column profile layout shared by /profile (the owner) and
 * /u/[username] (read-only): the identity card on the left and a tabbed main
 * pane. On desktop the page is exactly one screen: the card stays put
 * (scrolling inside itself if it must) and only the tab content scrolls, in
 * ProfilePanel. Below 900px the card becomes a compact header above the tabs
 * and the page scrolls as usual.
 */
export function ProfileLayout({
  banner,
  aside,
  tabs,
  children,
}: {
  banner?: ReactNode;
  aside: ReactNode;
  tabs?: ProfileTabConfig;
  children: ReactNode;
}) {
  // Stable while the set of tabs is, so the readers don't re-render for nothing.
  const signature = tabs ? `${tabs.fallback}|${tabs.keys.join(",")}` : "";
  const config = useMemo<ProfileTabConfig | null>(() => {
    if (!signature) return null;
    const [fallback, keys] = signature.split("|");
    return { fallback, keys: keys.split(",") };
  }, [signature]);
  return (
    <TabConfigContext.Provider value={config}>
    <main className={styles.page}>
      <div className={styles.wrap}>
        {banner}
        <div className={styles.columns}>
          <aside className={styles.aside}>{aside}</aside>
          <div className={styles.pane}>{children}</div>
        </div>
      </div>
    </main>
    </TabConfigContext.Provider>
  );
}

/**
 * The tab panels under ProfileTabs. Every panel stays mounted: the open one
 * shows, the rest sit in hidden <Activity> boundaries (pre-rendered at idle
 * priority, effects paused), so a tab click only swaps which one is visible.
 * Panels render from data the page already loaded; one still waiting shows
 * its own skeleton.
 */
export function ProfilePanels<K extends string>({ panels }: { panels: Partial<Record<K, ReactNode>> }) {
  const active = useOpenTab();
  // A section the API left out (null or false) has no panel.
  const keys = (Object.keys(panels) as K[]).filter((key) => panels[key] != null && panels[key] !== false);
  return (
    <>
      {keys.map((key) => (
        <Activity key={key} mode={key === active ? "visible" : "hidden"} name={`panel-${key}`}>
          <ProfilePanel tab={key}>{panels[key]}</ProfilePanel>
        </Activity>
      ))}
    </>
  );
}

/**
 * One tab's panel: the scrolling region on desktop, with a soft fade at the
 * bottom while there's more below. Hiding drops the scroll position, so it's
 * kept here and put back (before paint) when the tab opens again.
 */
function ProfilePanel({ tab, children }: { tab: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const scrollTop = useRef(0);

  // Layout effects run again each time the hidden Activity shows.
  useLayoutEffect(() => {
    const panel = ref.current;
    if (!panel) return;
    panel.scrollTop = scrollTop.current;
    const update = () => {
      panel.toggleAttribute("data-more", panel.scrollTop + panel.clientHeight < panel.scrollHeight - 1);
    };
    const onScroll = () => {
      scrollTop.current = panel.scrollTop;
      update();
    };
    update();
    // The content grows as sections load, and the panel resizes with the window.
    const observer = new ResizeObserver(update);
    observer.observe(panel);
    if (panel.firstElementChild) observer.observe(panel.firstElementChild);
    panel.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer.disconnect();
      panel.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <div ref={ref} id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className={styles.panel} data-profile-panel>
      <div className={styles.main}>{children}</div>
    </div>
  );
}

export function IdentityCard({
  avatar,
  name,
  username,
  accountLabel,
  links,
  social,
  notice,
  bio,
  region,
  joined,
  rank,
  rankDetail,
  province,
  streak,
  streakGrew = false,
  badges,
  action,
  footer,
}: {
  avatar: ReactNode;
  name: string;
  username: string | null;
  /** The "Trekly team" or "Demo account" badge, under the name. */
  accountLabel?: AccountLabel | null;
  /** "View public profile" and similar, under the username. */
  links?: ReactNode;
  /** Follower and following counts, under the name. */
  social?: ReactNode;
  /** Under the name, e.g. photo upload progress and errors. */
  notice?: ReactNode;
  bio?: string | null;
  region?: string | null;
  joined?: string | null;
  rank?: Rank | null;
  /** Under the rank name: the owner's progress (visitors get the name and emblem only). */
  rankDetail?: ReactNode;
  /** Home province or territory code, beside the rank; null hides it. */
  province?: string | null;
  /** Visit streak; hidden below 2 days. */
  streak?: StreakCounts | null;
  /** The streak just grew: its flame animates once. */
  streakGrew?: boolean;
  badges?: ReactNode;
  action?: ReactNode;
  footer?: ReactNode;
}) {
  const home = findProvince(province);
  const best = showsStreak(streak) ? bestLabel(streak) : null;
  return (
    <div className={styles.card}>
      <div className={styles.identity}>
        <div className={styles.avatarSlot}>{avatar}</div>
        <div className={styles.identityText}>
          <h1 className={styles.name}>{name}</h1>
          {username && <p className={styles.username}>@{username}</p>}
          {accountLabel && (
            <p className={styles.accountLabel}>
              <AccountBadge label={accountLabel} />
            </p>
          )}
          {joined && (
            <p className={styles.joined}>
              <CalendarDays size={14} aria-hidden="true" />
              {joined}
            </p>
          )}
          {links && <div className={styles.links}>{links}</div>}
        </div>
      </div>

      {social}

      {notice}

      {bio && <p className={styles.bio}>{bio}</p>}

      {(region || showsStreak(streak)) && (
        <ul className={styles.meta}>
          {region && (
            <li>
              <MapPin size={16} aria-hidden="true" />
              {region}
            </li>
          )}
          {showsStreak(streak) && (
            <li className={styles.streak}>
              <StreakFlame size={16} grew={streakGrew} />
              <span className={styles.streakDays}>{streakLabel(streak.current)}</span>
              {best && <span className={styles.streakBest}>{best}</span>}
            </li>
          )}
        </ul>
      )}

      {(rank || home) && (
        <div className={styles.rankRow}>
          {rank && (
            <div className={styles.rank}>
              <RankEmblem level={rank.level} className={styles.rankEmblem} />
              <div className={styles.rankText}>
                <p className={styles.rankTitle}>
                  <span className={ui.srOnly}>Rank: </span>
                  {rank.title}
                </p>
                {rankDetail}
              </div>
            </div>
          )}
          {home && (
            <div className={styles.home}>
              <ProvinceBadgeCard province={home} className={styles.homeTrigger}>
                <ProvinceBadge province={home} decorative className={styles.homeBadge} />
              </ProvinceBadgeCard>
            </div>
          )}
        </div>
      )}

      {badges}

      {action && <div className={styles.action}>{action}</div>}

      {footer && <div className={styles.footer}>{footer}</div>}
    </div>
  );
}

/** The home province badge's card: "Home province: Alberta". */
function ProvinceBadgeCard({ province, className, children }: { province: Province; className?: string; children: ReactNode }) {
  const title = `${homeLabel(province)}: ${province.name}`;
  return (
    <DetailCard
      label={title}
      className={className}
      body={<BadgeCardBody art={<ProvinceBadge province={province} decorative />} title={title} />}
    >
      {children}
    </DetailCard>
  );
}

/**
 * A trail stamp's card: the stamp, the trail's name and park, its difficulty
 * and when it was hiked, with a link to the trail.
 */
function TrailBadgeCard({
  trail,
  hikedOn,
  datesHidden,
  owner,
  mine,
  className,
  children,
}: {
  trail: TrailListItem;
  hikedOn: string | null | undefined;
  datesHidden: boolean;
  owner: string;
  mine: boolean;
  className?: string;
  children: ReactNode;
}) {
  const hiked = trailBadgeHiked(hikedOn, datesHidden);
  return (
    <DetailCard
      label={`${trail.name}: ${mine ? "your" : `${owner}'s`} trail badge details`}
      dialogLabel={`${trail.name} badge details`}
      earned
      className={className}
      body={
        <BadgeCardBody
          art={<TrailBadge name={trail.name} terrain={trail.terrain} colour={groupColour(`region:${trail.region}`)} hiked />}
          status={mine ? "Trail badge" : `${owner}'s trail badge`}
          title={trail.name}
          sub={trail.park_name ?? trail.region}
          earned
        >
          <CardLine muted>
            <span>{TERRAIN_LABELS[trail.terrain]}</span>
            {hiked && <span>{hiked}</span>}
          </CardLine>
        </BadgeCardBody>
      }
      footer={<Link href={trailHref(trail)}>Open the trail page</Link>}
    >
      {children}
    </DetailCard>
  );
}

/** A featured badge's art: the trail's Trail Journal badge, a milestone medal or the province badge. */
export function BadgeArt({ badge, className }: { badge: FeaturedBadge; className?: string }) {
  if (badge.kind === "province") {
    const home = findProvince(badge.province);
    return home ? <ProvinceBadge province={home} className={className} /> : null;
  }
  if (badge.kind === "milestone") {
    return <MilestoneBadge icon={badge.badge.icon} tier={badge.badge.tier} title={badgeName(badge)} className={className} />;
  }
  const { trail } = badge;
  return <TrailBadge name={trail.name} terrain={trail.terrain} colour={groupColour(`region:${trail.region}`)} hiked className={className} />;
}

/**
 * The identity card's three featured badge slots. A trail badge opens its
 * trail, its name showing on hover and focus; a milestone opens its details
 * card (MilestoneBadgeCard). Owners also see empty slots,
 * the Edit button and, with no badges yet, how to earn one; visitors see
 * only filled slots, and nothing at all without any.
 */
export function FeaturedBadgeSlots({
  badges,
  ownerName,
  mine = false,
  loading = false,
  datesHidden = false,
  onEdit,
}: {
  badges: FeaturedBadge[];
  /** The owner hides their hike dates from this viewer. */
  datesHidden?: boolean;
  /** The profile's display name, for milestone cards ("Earned by Ana"). */
  ownerName: string;
  /** The viewer is looking at their own badges. */
  mine?: boolean;
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
          const art = <BadgeArt badge={badge} className={styles.badge} />;
          return (
            <li key={badgeKey(badge)} className={styles.badgeSlot}>
              {badge.kind === "trail" ? (
                <TrailBadgeCard
                  trail={badge.trail}
                  hikedOn={badge.hiked_on}
                  datesHidden={datesHidden}
                  owner={ownerName}
                  mine={mine}
                  className={styles.badgeLink}
                >
                  {art}
                </TrailBadgeCard>
              ) : badge.kind === "milestone" ? (
                <MilestoneBadgeCard badge={badge.badge} owner={ownerName} mine={mine} className={styles.badgeLink}>
                  {art}
                </MilestoneBadgeCard>
              ) : findProvince(badge.province) ? (
                <ProvinceBadgeCard province={findProvince(badge.province)!} className={styles.badgeLink}>
                  {art}
                </ProvinceBadgeCard>
              ) : null}
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
  onChange,
  label,
}: {
  tabs: TabItem<K>[];
  onChange: (key: K) => void;
  label: string;
}) {
  const active = useOpenTab();
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
    <div id="profile-tabs" className={styles.tabBar} data-fade-start={fade.start || undefined} data-fade-end={fade.end || undefined}>
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
            </div>
          </aside>
          <div className={styles.pane}>
            <div className={`${ui.skeleton} ${styles.skeletonTabs}`} />
            <div className={`${ui.skeleton} ${styles.skeletonSection}`} />
            <div className={`${ui.skeleton} ${styles.skeletonSection}`} />
          </div>
        </div>
      </div>
    </main>
  );
}
