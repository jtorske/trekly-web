/**
 * What the frontend may send to Sentry (instrumentation-client.ts and the
 * server/edge configs): Sentry's beforeSend. Mirrors backend
 * app/observability.py.
 *
 * - Expected errors are dropped: API 4xx answers (signed out, forbidden,
 *   not found, validation, moderation rejections, rate limits), Supabase
 *   auth 4xx (wrong password and the like) and aborted requests.
 * - Personal data is removed wherever it appears: anything shaped like an
 *   email address or a JWT, auth headers, cookies, token/code/email URL
 *   parameters (Supabase puts session tokens in the URL hash after sign-in),
 *   and the user object except its id.
 */

export const FILTERED = "[Filtered]";
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const JWT = /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g;
const SENSITIVE_HEADERS = new Set(["authorization", "cookie", "set-cookie", "apikey", "x-api-key", "proxy-authorization"]);
/** Keys whose values are secrets or personal; "code"/"key" only on their own (not province_code). */
const SENSITIVE_KEY = /token|secret|password|signature|email|api_?key|^code$|^key$/i;

type Json = Record<string, unknown>;
const isObject = (value: unknown): value is Json => typeof value === "object" && value !== null && !Array.isArray(value);

export function scrubText(value: string): string {
  return value.replace(EMAIL, FILTERED).replace(JWT, FILTERED);
}

/** URL with sensitive query and hash parameters blanked (and emails/JWTs anywhere). */
export function scrubUrl(value: string): string {
  const blank = (part: string) =>
    part
      .split("&")
      .map((pair) => {
        const [key] = pair.split("=");
        return pair.includes("=") && SENSITIVE_KEY.test(decodeURIComponent(key)) ? `${key}=${FILTERED}` : pair;
      })
      .join("&");
  const [beforeHash, hash] = splitOnce(value, "#");
  const [path, query] = splitOnce(beforeHash, "?");
  let out = path;
  if (query !== null) out += `?${blank(query)}`;
  if (hash !== null) out += `#${hash.includes("=") ? blank(hash) : hash}`;
  return scrubText(out);
}

function splitOnce(value: string, separator: string): [string, string | null] {
  const at = value.indexOf(separator);
  return at === -1 ? [value, null] : [value.slice(0, at), value.slice(at + 1)];
}

function scrub(value: unknown): unknown {
  if (typeof value === "string") return /^https?:\/\//.test(value) ? scrubUrl(value) : scrubText(value);
  if (Array.isArray(value)) return value.map(scrub);
  if (isObject(value)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, typeof item === "string" && SENSITIVE_KEY.test(key) ? FILTERED : scrub(item)]),
    );
  }
  return value;
}

/** An API or auth answer in the 4xx range, or an aborted request: normal life, not a bug. */
export function isExpectedError(error: unknown): boolean {
  if (!isObject(error) && !(error instanceof Error)) return false;
  const { name, status } = error as { name?: unknown; status?: unknown };
  if (name === "AbortError") return true;
  const clientError = typeof status === "number" && status >= 400 && status < 500;
  return clientError && (name === "ApiError" || (typeof name === "string" && name.startsWith("Auth")));
}

/** Sentry's beforeSend: null drops the event. */
export function scrubEvent<E>(event: E, hint?: { originalException?: unknown }): E | null {
  if (isExpectedError(hint?.originalException)) return null;
  if (!isObject(event)) return event;
  const out: Json = { ...event };
  if (isObject(out.request)) {
    const request: Json = { ...out.request };
    delete request.cookies;
    delete request.data;
    if (isObject(request.headers)) {
      request.headers = Object.fromEntries(
        Object.entries(request.headers).map(([key, value]) => [
          key,
          SENSITIVE_HEADERS.has(key.toLowerCase()) || key.toLowerCase().includes("token") ? FILTERED : scrub(value),
        ]),
      );
    }
    if (typeof request.url === "string") request.url = scrubUrl(request.url);
    if (typeof request.query_string === "string") request.query_string = scrubUrl(`?${request.query_string}`).slice(1);
    out.request = request;
  }
  if (isObject(out.user)) out.user = typeof out.user.id === "string" ? { id: out.user.id } : {};
  for (const key of ["message", "logentry", "exception", "breadcrumbs", "extra", "contexts", "tags"]) {
    if (key in out) out[key] = scrub(out[key]);
  }
  return out as E;
}
