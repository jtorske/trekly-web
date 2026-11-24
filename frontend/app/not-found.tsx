import type { Metadata } from "next";
import StatusPage from "@/components/StatusPage";

// Replaces Next's default 404, whose dark-mode styles put white text on the
// site's cream background.
export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <StatusPage eyebrow="404 · Page not found" title="This trail doesn't go anywhere">
      <p>The page you&apos;re looking for doesn&apos;t exist or has moved. There are plenty of trails that do, though.</p>
    </StatusPage>
  );
}
