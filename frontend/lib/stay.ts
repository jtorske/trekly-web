/**
 * A stay (first night, number of nights, party size) and how it travels in
 * the URL, so a check or an alert survives a sign-in round trip. Dates are
 * plain YYYY-MM-DD strings handled in UTC, so no time zone can shift a night.
 */

import type { NightStatus, Stay, StaySummary } from "./availabilityApi";

const MAX_NIGHTS = 14;
const MAX_PARTY = 12;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * A complete YYYY-MM-DD date. Date inputs report partial values while someone
 * types (a 5- or 6-digit year, say), which must not reach the stay.
 */
export function isPlainDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function toISODate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return toISODate(date);
}

/** Today in the user's own calendar, as YYYY-MM-DD. */
export function localToday(now = new Date()): string {
  return toISODate(new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())));
}

/** Two weeks out: far enough to plan, near enough to likely be bookable. */
export function defaultStay(today: string, typicalNights: number | null): Stay {
  const nights = Math.min(Math.max(typicalNights ?? 1, 1), MAX_NIGHTS);
  return { start: addDays(today, 14), nights, party: 2 };
}

function clampInt(value: string | null, min: number, max: number): number | null {
  if (value === null || !/^\d+$/.test(value)) return null;
  const n = Number(value);
  return n >= min && n <= max ? n : null;
}

/** The stay in ?start=&nights=&party=, or null if absent or invalid. */
export function stayFromParams(params: URLSearchParams, today: string): Stay | null {
  const start = params.get("start");
  if (!start || !isPlainDate(start) || start < today) return null;
  const nights = clampInt(params.get("nights"), 1, MAX_NIGHTS);
  if (nights === null) return null;
  const party = clampInt(params.get("party"), 1, MAX_PARTY) ?? 2;
  return { start, nights, party };
}

/**
 * A Parks Canada booking form opened on these dates. Verified 2026-10-15:
 * startDate/endDate fill in the arrival date and the nights of the first
 * itinerary row. No parameter sets party size. Other URLs pass through.
 */
export function withStayDates(url: string, start: string, nights: number): string {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }
  if (parsed.hostname !== "reservation.pc.gc.ca") return url;
  parsed.searchParams.set("startDate", start);
  parsed.searchParams.set("endDate", addDays(start, nights));
  return parsed.toString();
}

export function stayParams(stay: Stay): Record<string, string> {
  return { start: stay.start, nights: String(stay.nights), party: String(stay.party) };
}

const DAY = new Intl.DateTimeFormat("en-CA", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
const SHORT = new Intl.DateTimeFormat("en-CA", { weekday: "short", day: "numeric", timeZone: "UTC" });

export function formatDay(iso: string): string {
  return DAY.format(new Date(`${iso}T00:00:00Z`));
}

/** Compact label for one night cell, e.g. "Tue 20". */
export function formatNight(iso: string): string {
  return SHORT.format(new Date(`${iso}T00:00:00Z`));
}

/** "Tue, Oct 20 – Thu, Oct 22 · 2 nights" (the second date is the morning you leave). */
export function formatStay(start: string, nights: number): string {
  return `${formatDay(start)} – ${formatDay(addDays(start, nights))} · ${nights} ${nights === 1 ? "night" : "nights"}`;
}

export const NIGHT_LABELS: Record<NightStatus, string> = {
  available: "Available",
  full: "Full",
  closed: "Closed for the season",
  not_released: "Not bookable yet",
  unknown: "Unknown",
};

export const SUMMARY_LABELS: Record<StaySummary, string> = {
  available: "Available every night",
  partial: "Some nights available",
  full: "Full",
  closed: "Closed for the season",
  not_released: "Not bookable yet",
  unknown: "Couldn't tell",
};

/** Ends a sentence with a full stop unless it already has one (e.g. "2:41 p.m."). */
export function sentence(text: string): string {
  return text.endsWith(".") ? text : `${text}.`;
}

/** Alerts make sense when the stay isn't fully available and could open up. */
export function canAlert(summary: StaySummary): boolean {
  return summary === "partial" || summary === "full" || summary === "not_released";
}
