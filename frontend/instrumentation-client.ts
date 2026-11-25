// Sentry in the browser: error reporting only. Off until
// NEXT_PUBLIC_SENTRY_DSN is set; no tracing and no session replay (neither
// is in the bundle). See lib/sentryOptions.ts.
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "@/lib/sentryOptions";

const options = sentryOptions();
if (options.enabled) Sentry.init(options);
