/**
 * Visit streaks: how many days in a row a signed-in user has visited.
 *
 * The server owns every rule and count (backend app/streaks.py); the browser
 * only sends its IANA time zone, once per app load and at most once a day.
 * Here: the once-a-day guard, which caches the server's reply in
 * sessionStorage, and the wording. A weekly streak would change the labels
 * below and `period()` on the server.
 */

export interface VisitReply {
  current_streak: number;
  longest_streak: number;
  /** The date the visit counted for (YYYY-MM-DD, the user's time zone). */
  today: string;
  /** This visit made the streak longer: the icon animates once. */
  grew: boolean;
}

export interface StreakCounts {
  current: number;
  longest: number;
}

/** What's cached per tab, so a reload the same day doesn't call the API. */
export interface CachedVisit extends StreakCounts {
  userId: string;
  today: string;
}

export const CACHE_KEY = "trekly.visit";

/** The browser's IANA zone ("America/Edmonton"), or null if it can't say. */
export function browserTimeZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/** YYYY-MM-DD for `now` in `timeZone` (the browser's own zone when null). */
export function localDate(now: Date, timeZone: string | null): string {
  const format = (zone: string | undefined) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  try {
    return format(timeZone ?? undefined);
  } catch {
    return format(undefined);
  }
}

export function readCache(raw: string | null): CachedVisit | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<CachedVisit>;
    if (
      typeof value.userId === "string" &&
      typeof value.today === "string" &&
      Number.isInteger(value.current) &&
      Number.isInteger(value.longest)
    ) {
      return value as CachedVisit;
    }
  } catch {
    // Unreadable: treat as not recorded.
  }
  return null;
}

/** The cached counts if this user's visit is already recorded for `today`; null means call the API. */
export function cachedToday(cache: CachedVisit | null, userId: string, today: string): StreakCounts | null {
  if (!cache || cache.userId !== userId || cache.today !== today) return null;
  return { current: cache.current, longest: cache.longest };
}

export function toCache(userId: string, reply: VisitReply): CachedVisit {
  return { userId, today: reply.today, current: reply.current_streak, longest: reply.longest_streak };
}

/** A streak of 1 is just a visit: shown from 2 days. */
export const showsStreak = (streak: StreakCounts | null | undefined): streak is StreakCounts =>
  Boolean(streak && streak.current >= 2);

export const streakLabel = (days: number) => `${days}-day streak`;

/** "Best: 30 days", only when the best is longer than the current streak. */
export const bestLabel = (streak: StreakCounts): string | null =>
  streak.longest > streak.current ? `Best: ${streak.longest} days` : null;
