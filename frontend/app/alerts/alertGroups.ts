import type { CampgroundAlert } from "../../lib/availabilityApi.ts";

export type AlertGroupKey = "active" | "found" | "past";

export interface AlertGroup {
  key: AlertGroupKey;
  title: string;
  alerts: CampgroundAlert[];
}

const TITLES: Record<AlertGroupKey, string> = {
  active: "Active",
  found: "Found",
  past: "Past and cancelled",
};

/**
 * Which section a card sits in. A stay whose first night has passed is past
 * whatever its status: the poller expires active ones on its next run, and a
 * notified one can no longer be booked.
 */
export function groupOf(alert: Pick<CampgroundAlert, "status" | "start_date">, today: string): AlertGroupKey {
  if (alert.status === "cancelled" || alert.status === "expired" || alert.start_date < today) return "past";
  return alert.status === "notified" ? "found" : "active";
}

/** Active and Found soonest first; Past most recent first. Empty groups are left out. */
export function groupAlerts(alerts: CampgroundAlert[], today: string): AlertGroup[] {
  const groups: Record<AlertGroupKey, CampgroundAlert[]> = { active: [], found: [], past: [] };
  for (const alert of alerts) groups[groupOf(alert, today)].push(alert);
  groups.active.sort((a, b) => a.start_date.localeCompare(b.start_date));
  groups.found.sort((a, b) => a.start_date.localeCompare(b.start_date));
  groups.past.sort((a, b) => b.start_date.localeCompare(a.start_date));
  return (Object.keys(groups) as AlertGroupKey[])
    .filter((key) => groups[key].length > 0)
    .map((key) => ({ key, title: TITLES[key], alerts: groups[key] }));
}

const OLDER = new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric" });

/** "just now", "12 min ago", "3 h ago", then a date. */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `on ${OLDER.format(new Date(iso))}`;
}

/** The site code is shown only when it adds something ("Evelyn Creek 27"). */
export function alertPlace(alert: Pick<CampgroundAlert, "campground" | "site_code">): string {
  return alert.site_code && alert.site_code !== alert.campground
    ? `${alert.campground} ${alert.site_code}`
    : alert.campground;
}
