// Sentry in the browser. Off until NEXT_PUBLIC_SENTRY_DSN is set; no
// session replay (not even the integration). See lib/sentryOptions.ts.
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "@/lib/sentryOptions";

const options = sentryOptions();
if (options.enabled) Sentry.init(options);

// Navigation timing for the 10% of traced page loads.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
