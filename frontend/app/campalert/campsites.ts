export interface Trail {
  id: string;
  name: string;
  region: string;
}

const TRAILS: Trail[] = [
  { id: "t-loh", name: "Lake O'Hara", region: "Yoho National Park, BC" },
  { id: "t-berg", name: "Berg Lake Trail", region: "Mount Robson Provincial Park, BC" },
  { id: "t-tunnel", name: "Tunnel Mountain", region: "Banff National Park, AB" },
  { id: "t-assiniboine", name: "Mount Assiniboine", region: "Mount Assiniboine Provincial Park, BC" },
];

const SEARCH_DELAY_MS = 260;

export function searchTrails(query: string): Promise<Trail[]> {
  const q = query.trim().toLowerCase();

  return new Promise((resolve) => {
    window.setTimeout(() => {
      if (!q) {
        resolve([]);
        return;
      }

      resolve(
        TRAILS.filter(
          (trail) =>
            trail.name.toLowerCase().includes(q) ||
            trail.region.toLowerCase().includes(q),
        ),
      );
    }, SEARCH_DELAY_MS);
  });
}
