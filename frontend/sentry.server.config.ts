// Sentry in the Node server runtime (server components, route handlers,
// metadata and OG images). Loaded by instrumentation.ts; off without a DSN.
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "@/lib/sentryOptions";

const options = sentryOptions();
if (options.enabled) Sentry.init(options);
