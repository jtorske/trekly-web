import type { Terrain } from "./packingList";

export interface TrailSummary {
  id: string;
  name: string;
  region: string;
  terrain: Terrain;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function searchTrails(
  query: string,
  signal?: AbortSignal,
): Promise<TrailSummary[]> {
  const res = await fetch(
    `${API_BASE}/api/trails?q=${encodeURIComponent(query)}`,
    { signal },
  );
  if (!res.ok) throw new Error("Failed to search trails");
  return res.json();
}

export async function getTrail(id: string): Promise<TrailSummary | null> {
  const res = await fetch(`${API_BASE}/api/trails/${encodeURIComponent(id)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to load trail");
  return res.json();
}
