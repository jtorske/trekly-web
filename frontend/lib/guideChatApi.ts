import { apiFetch } from "./api";
import type { ChatResponse, ChatStatus } from "./guideChat";

/** Trekly Guide chat endpoints (signed in only). */
export const getChatStatus = (signal?: AbortSignal) =>
  apiFetch<ChatStatus>("/api/guide/chat/status", { auth: true, signal });

export const sendChat = (body: { messages: { role: string; content: string }[]; shown_trail_ids: string[] }) =>
  apiFetch<ChatResponse>("/api/guide/chat", { method: "POST", body, auth: true });
