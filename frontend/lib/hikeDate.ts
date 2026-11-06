/**
 * Labels for hikes with no date: ones picked from "Which of these have you
 * hiked?" or "Add past hikes", from before the hiker joined Trekly.
 */

/** "Nov 2026" from an ISO timestamp, or null if there isn't one. */
export function joinMonth(joinedAt: string | null | undefined): string | null {
  if (!joinedAt) return null;
  const when = new Date(joinedAt);
  if (Number.isNaN(when.getTime())) return null;
  return when.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

/**
 * "Hiked before Nov 2026" (or "Hiked before Trekly" when the join date isn't
 * known, as for visitors to a public profile). `prefix` false drops "Hiked".
 */
export function undatedLabel(joinedAt: string | null | undefined, prefix = true): string {
  const month = joinMonth(joinedAt);
  const before = `before ${month ?? "Trekly"}`;
  return prefix ? `Hiked ${before}` : before.charAt(0).toUpperCase() + before.slice(1);
}
