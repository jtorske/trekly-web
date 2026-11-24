"use client"; // Error boundaries must be Client Components

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";
import StatusPage from "@/components/StatusPage";
import ui from "@/components/ui.module.css";
import "./globals.css";

/**
 * Only when the root layout itself fails (the header, auth provider, etc.).
 * It replaces the whole layout, so it brings its own html and body; the
 * brand fonts don't load here, and the type falls back to Georgia and the
 * system sans (see globals.css).
 */
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
    // A no-op until Sentry is configured (lib/sentryOptions.ts).
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">
        <title>Something went wrong | Trekly</title>
        <StatusPage
          eyebrow="Something went wrong"
          title="We lost the trail for a moment"
          actions={
            <button type="button" className={ui.primary} onClick={() => unstable_retry()}>
              Try again
            </button>
          }
        >
          <p>Trekly hit a snag while loading. It&apos;s usually temporary, so give it another go.</p>
          {error.digest && <p>Reference: {error.digest}</p>}
        </StatusPage>
      </body>
    </html>
  );
}
