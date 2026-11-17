/**
 * People search and "Hikers you might know" (pure, so it's unit tested).
 * The API decides who appears and in what order (app/hiker_search.py and the
 * database functions behind it); nothing here hides anyone.
 */

import type { FollowState } from "./follows.ts";

export type SearchTab = "trails" | "hikers";
export const SEARCH_TABS: { key: SearchTab; label: string }[] = [
  { key: "trails", label: "Trails" },
  { key: "hikers", label: "Hikers" },
];

/** The API wants at least this many characters (after a leading @). */
export const MIN_QUERY = 2;
export const MAX_QUERY = 60;
/** Typing pauses this long before a search goes out. */
export const SEARCH_DEBOUNCE_MS = 300;
/** Results per page on /search. */
export const PAGE_SIZE = 20;
/** Rows in the Activity page's "Find hikers" dropdown. */
export const DROPDOWN_ROWS = 5;

export const TAB_STORAGE_KEY = "trekly:search-tab";

export interface HikerResult {
  username: string;
  display_name: string | null;
  avatar_path: string | null;
  is_private: boolean;
  follow: FollowState;
  /** Only when they show their rank (and you may see their profile). */
  rank: { level: number; title: string } | null;
  /** Two-letter code or "outside", only when they show it. */
  home_province: string | null;
  /** Trails you've both hiked; null while their journal isn't visible to you. */
  common_trails: number | null;
  /** Suggestions: from your home province. */
  same_province: boolean;
}

export interface HikerPage {
  items: HikerResult[];
  next_offset: number | null;
}

/** The query as the API matches it: trimmed, without a leading @. */
export function searchTerm(q: string): string {
  return q.trim().replace(/^@+/, "").trim();
}

export function isSearchable(q: string): boolean {
  return searchTerm(q).length >= MIN_QUERY;
}

export function parseTab(value: string | null | undefined): SearchTab | null {
  return value === "trails" || value === "hikers" ? value : null;
}

/** The tab to open: the URL's, else the last one used, else Trails. */
export function initialTab(fromUrl: string | null | undefined, remembered: string | null | undefined): SearchTab {
  return parseTab(fromUrl) ?? parseTab(remembered) ?? "trails";
}

export function searchHref(tab: SearchTab, q = ""): string {
  const params = new URLSearchParams({ tab });
  if (q.trim()) params.set("q", q.trim());
  return `/search?${params}`;
}

/**
 * Explore's box got "@name": the people search for "name", or null. Only a
 * leading @ counts, and there has to be something after it.
 */
export function hikerSearchHint(input: string): string | null {
  if (!input.trimStart().startsWith("@")) return null;
  const term = searchTerm(input);
  return term ? searchHref("hikers", term) : null;
}

/** "You've both hiked 3 trails"; null when there's nothing to say. */
export function commonTrailsLabel(count: number | null): string | null {
  if (!count || count < 1) return null;
  return `You've both hiked ${count.toLocaleString("en-CA")} ${count === 1 ? "trail" : "trails"}`;
}

/** Why a suggestion is there: trails in common first, then the province. */
export function suggestionReason(hiker: HikerResult, provinceName: string | null): string | null {
  const trails = commonTrailsLabel(hiker.common_trails);
  if (trails) return trails;
  if (hiker.same_province) return provinceName ? `Also from ${provinceName}` : "From your home province";
  return null;
}

export function hikerName(hiker: Pick<HikerResult, "display_name" | "username">): string {
  return hiker.display_name?.trim() || `@${hiker.username}`;
}

/** A private profile you can't see shows only its name, username and photo. */
export function isLimited(hiker: HikerResult): boolean {
  return hiker.is_private && hiker.follow !== "following";
}
