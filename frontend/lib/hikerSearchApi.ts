import { apiFetch } from "./api";
import { PAGE_SIZE, searchTerm, type HikerPage, type HikerResult } from "./hikerSearch";

/** People search (signed in only). Rate-limited: a 429 says to wait. */
export function searchHikers(q: string, { offset = 0, limit = PAGE_SIZE, signal }: { offset?: number; limit?: number; signal?: AbortSignal } = {}) {
  const params = new URLSearchParams({ q: searchTerm(q), offset: String(offset), limit: String(limit) });
  return apiFetch<HikerPage>(`/api/search/hikers?${params}`, { auth: true, signal });
}

export const getSuggestedHikers = (signal?: AbortSignal) =>
  apiFetch<{ items: HikerResult[] }>("/api/me/suggested-hikers", { auth: true, signal });
