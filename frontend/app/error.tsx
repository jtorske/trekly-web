"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";
import StatusPage from "@/components/StatusPage";
import ui from "@/components/ui.module.css";

/**
 * Any page that throws while rendering lands here, inside the site's header
 * and footer. "Try again" re-fetches and re-renders the page (most failures
 * are Render's API waking up); the reference matches the server's logs.
 */
export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <StatusPage
      eyebrow="Something went wrong"
      title="We lost the trail for a moment"
      actions={
        <button type="button" className={ui.primary} onClick={() => unstable_retry()}>
          Try again
        </button>
      }
    >
      <p>This page hit a snag while loading. It&apos;s usually temporary, so give it another go.</p>
      {error.digest && <p>Reference: {error.digest}</p>}
    </StatusPage>
  );
}
