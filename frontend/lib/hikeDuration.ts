/**
 * "Time on trail" on a hike: hours and minutes in the dialog, minutes in the
 * API (hike_logs.duration_minutes, 10 min to 14 days). Trekly Guide compares
 * it with the trail's estimate to learn the hiker's pace.
 */
export const MIN_DURATION_MINUTES = 10;
export const MAX_DURATION_MINUTES = 14 * 24 * 60;

/** Both boxes empty: null (no time). Otherwise minutes, or "invalid". */
export function toMinutes(hours: string, minutes: string): number | null | "invalid" {
  const h = hours.trim();
  const m = minutes.trim();
  if (!h && !m) return null;
  if ((h && !/^\d+$/.test(h)) || (m && !/^\d+$/.test(m))) return "invalid";
  const total = Number(h || 0) * 60 + Number(m || 0);
  if (Number(m || 0) > 59 || total < MIN_DURATION_MINUTES || total > MAX_DURATION_MINUTES) return "invalid";
  return total;
}

export function fromMinutes(total: number | null | undefined): { hours: string; minutes: string } {
  if (total == null) return { hours: "", minutes: "" };
  return { hours: String(Math.floor(total / 60)), minutes: String(total % 60) };
}
