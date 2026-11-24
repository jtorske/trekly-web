// Sentry in the edge runtime. Loaded by instrumentation.ts; off without a DSN.
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "@/lib/sentryOptions";

const options = sentryOptions();
if (options.enabled) Sentry.init(options);
