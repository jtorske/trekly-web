/**
 * Trekly Guide chat in the browser. The conversation lives here only: in
 * memory, and in sessionStorage so closing and reopening the panel in the
 * same tab keeps it. The server never stores it; each message sends the last
 * MAX_TURNS turns (backend app/routers/guide_chat.py).
 */
import type { TrailListItem } from "./trailsApi.ts";

export const MAX_TURNS = 10;
export const MAX_MESSAGE_CHARS = 600;
const STORAGE_KEY = "trekly:guide-chat";

export interface TrailCard {
  type: "trail";
  trail: TrailListItem | null;
  reasons: string[];
  est_label: string | null;
  dog_note: string | null;
  dog_policy: string;
}

export interface ReadinessCardData {
  type: "readiness";
  slug: string;
  name: string;
  verdict: "ready" | "stretch" | "not_yet";
  label: string;
  date: string;
  est_label: string | null;
  reasons: { level: string; text: string }[];
  build_up: { slug: string; name: string }[];
  avalanche_link: string | null;
}

export type ChatCard = TrailCard | ReadinessCardData;

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  cards?: ChatCard[];
  quickReplies?: string[];
}

export interface ChatResponse {
  mode: "chat" | "fallback_to_form" | "blocked";
  text: string;
  cards: ChatCard[];
  quick_replies: string[];
  reason: string | null;
  remaining_today: number;
}

export interface ChatStatus {
  available: boolean;
  remaining_today: number;
  daily_limit: number;
}

/** What goes to the server: the last MAX_TURNS turns, text only (no cards). */
export function requestTurns(history: ChatTurn[]): { role: string; content: string }[] {
  return history.slice(-MAX_TURNS).map(({ role, content }) => ({ role, content: content.slice(0, 1200) }));
}

/** Trails already shown as cards, so "show me more" skips them. */
export function shownTrailIds(history: ChatTurn[]): string[] {
  const ids = history.flatMap((turn) =>
    (turn.cards ?? []).flatMap((card) => (card.type === "trail" && card.trail ? [card.trail.id] : [])),
  );
  return [...new Set(ids)].slice(-60);
}

interface Store {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function store(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function loadHistory(storage: Store | null = store()): ChatTurn[] {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((t) => t && (t.role === "user" || t.role === "assistant")) : [];
  } catch {
    return [];
  }
}

export function saveHistory(history: ChatTurn[], storage: Store | null = store()): void {
  try {
    if (history.length === 0) storage?.removeItem(STORAGE_KEY);
    else storage?.setItem(STORAGE_KEY, JSON.stringify(history.slice(-30)));
  } catch {
    // Private mode or full storage: the chat still works for this visit.
  }
}

export function clearHistory(storage: Store | null = store()): void {
  try {
    storage?.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

export const STARTER_PROMPTS = ["Plan a hike this weekend", "Something easy near me", "Am I ready for a big day?"];
