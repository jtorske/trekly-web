/**
 * Trail data for server rendering (trail pages, Explore's first results,
 * the sitemap and the old-URL redirect). Cached by Next for a few minutes,
 * so crawlers and visitors don't each hit the API; a photo approved on
 * /admin/photos shows within that window.
 */
import type { SeasonInfo } from "./seasonMode";
import type { SeasonMode, TrailDetail, TrailSearchRequest, TrailSearchResult } from "./trailsApi";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REVALIDATE_SECONDS = 300;
// Render's free tier can take a while to wake; past this the page says it couldn't load.
const TIMEOUT_MS = 8000;

export class TrailApiUnavailable extends Error {}

async function getJson<T>(path: string, init: RequestInit = {}): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new TrailApiUnavailable(path);
  }
  if (response.status === 404 || response.status === 422) return null;
  if (!response.ok) throw new TrailApiUnavailable(`${path}: ${response.status}`);
  return (await response.json()) as T;
}

/** The trail at /trails/{slug}; null when there's none. Throws TrailApiUnavailable when the API is down. */
export function getTrailBySlug(slug: string): Promise<TrailDetail | null> {
  return getJson<TrailDetail>(`/api/trails/by-slug/${encodeURIComponent(slug)}`);
}

/** For the old /trails?id=… links. */
export function getTrailById(id: string): Promise<TrailDetail | null> {
  return getJson<TrailDetail>(`/api/trails/${encodeURIComponent(id)}`);
}

/** Explore's search, server side; null on any failure (the browser then fetches it). */
export async function searchExploreOnServer(request: TrailSearchRequest): Promise<TrailSearchResult | null> {
  try {
    return await getJson<TrailSearchResult>("/api/trails/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    return null;
  }
}

/** The current season (GET /api/season, backend app/season.py); null when the API can't say. */
export async function getSeasonOnServer(): Promise<SeasonMode | null> {
  try {
    return (await getJson<SeasonInfo>("/api/season"))?.season ?? null;
  } catch {
    return null;
  }
}

export interface SitemapTrail {
  slug: string;
  updated_at: string | null;
}

export interface SitemapProfile {
  username: string;
  updated_at: string | null;
}

export async function sitemapTrails(): Promise<SitemapTrail[]> {
  return (await getJson<SitemapTrail[]>("/api/trails/sitemap")) ?? [];
}

export async function sitemapProfiles(): Promise<SitemapProfile[]> {
  return (await getJson<SitemapProfile[]>("/api/sitemap/profiles")) ?? [];
}
