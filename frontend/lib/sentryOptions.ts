/**
 * Sentry.init options shared by the browser (instrumentation-client.ts), the
 * Node server and the edge runtime (sentry.*.config.ts). Free tier, errors
 * first:
 *
 * - Off unless NEXT_PUBLIC_SENTRY_DSN is set (Vercel → Production only).
 * - environment: "production" on Vercel's production deployment, "preview"
 *   on previews, "local" everywhere else; release: the git commit SHA. Both
 *   are inlined at build time by next.config.ts.
 * - No personal data (sendDefaultPii off, lib/sentryScrub.ts on every event),
 *   no session replay.
 * - Errors only, no tracing: next.config.ts compiles Sentry's tracing code
 *   out (__SENTRY_TRACING__ false), so phones download less before the
 *   first paint. Performance traces come from the API on Render instead.
 */
import { scrubEvent } from "./sentryScrub";

export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || undefined;
export const SENTRY_ENVIRONMENT = process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "local";
export const SENTRY_RELEASE = process.env.NEXT_PUBLIC_SENTRY_RELEASE || undefined;

export function sentryOptions() {
  return {
    dsn: SENTRY_DSN,
    enabled: Boolean(SENTRY_DSN),
    environment: SENTRY_ENVIRONMENT,
    release: SENTRY_RELEASE,
    sendDefaultPii: false,
    beforeSend: scrubEvent,
    beforeSendTransaction: scrubEvent,
    // Browser noise that isn't a Trekly bug.
    ignoreErrors: ["ResizeObserver loop limit exceeded", "ResizeObserver loop completed with undelivered notifications"],
  };
}
