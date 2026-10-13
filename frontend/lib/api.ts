import { getSupabaseClient } from "./supabaseClient";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function accessToken(forceRefresh = false): Promise<string | null> {
  const supabase = getSupabaseClient();
  if (forceRefresh) {
    const { data } = await supabase.auth.refreshSession();
    return data.session?.access_token ?? null;
  }
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

function messageFor(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) {
    return String(detail[0].msg).replace(/^Value error, /, "");
  }
  if (status === 401) return "Your session has ended. Sign in again.";
  if (status >= 500) return "Trekly is having trouble right now. Try again in a moment.";
  return "That request didn't work. Try again.";
}

/**
 * Fetch a Trekly API route. With `auth: true` the Supabase access token is
 * attached; on a 401 the session is refreshed once and the request retried,
 * so an expired access token doesn't bounce an active user to sign-in.
 */
export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean; signal?: AbortSignal } = {},
): Promise<T> {
  const { method = "GET", body, auth = false, signal } = options;

  const send = async (token: string | null) => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  };

  let response: Response;
  try {
    let token = auth ? await accessToken() : null;
    if (auth && !token) throw new ApiError("Sign in to continue.", 401);
    response = await send(token);
    if (auth && response.status === 401) {
      token = await accessToken(true);
      if (token) response = await send(token);
    }
  } catch (error) {
    if (error instanceof ApiError || (error as { name?: string }).name === "AbortError") throw error;
    throw new ApiError("We couldn't reach Trekly. Check your connection and try again.", 0);
  }

  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFor(response.status, payload), response.status);
  return payload as T;
}
