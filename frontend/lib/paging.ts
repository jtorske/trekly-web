/** One page of a list (pages count from 0); an out-of-range page is clamped to the last. */
export function pageOf<T>(items: T[], page: number, size: number): { items: T[]; page: number; pages: number } {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(0, page), pages - 1);
  return { items: items.slice(current * size, (current + 1) * size), page: current, pages };
}
