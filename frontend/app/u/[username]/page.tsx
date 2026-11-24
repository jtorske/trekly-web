import type { Metadata } from "next";
import { Suspense } from "react";
import type { PublicProfile } from "@/lib/profilesApi";
import { displayName, robotsFor } from "@/lib/publicProfile";
import { isIndexable, SITE_NAME } from "@/lib/site";
import PublicProfileView from "./PublicProfileView";

type Props = { params: Promise<{ username: string }> };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** The visitor view, for metadata only; null on any failure. */
async function fetchProfile(username: string): Promise<PublicProfile | null> {
  try {
    const response = await fetch(`${API_BASE}/api/profiles/${encodeURIComponent(username)}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    return response.ok ? ((await response.json()) as PublicProfile) : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { username } = await params;
  const profile = await fetchProfile(username);
  const title = profile ? `${displayName(profile)} (@${profile.username})` : "Profile";
  const description = profile && !profile.is_private ? profile.bio ?? `${displayName(profile)}'s hikes and gear on Trekly.` : undefined;
  return {
    title,
    description,
    // The card is ./opengraph-image.tsx. A page's openGraph replaces the
    // layout's whole object, so the site name and locale are repeated here.
    openGraph: { type: "profile", siteName: SITE_NAME, locale: "en_CA", title, description },
    twitter: { card: "summary_large_image", title, description },
    // noindex unless the owner turned on "Let search engines show my profile"
    // (and noindex if the API couldn't be reached to check).
    // Previews are never indexed, whatever the owner chose.
    robots: isIndexable() ? robotsFor(profile) : { index: false, follow: false },
    ...(profile ? { alternates: { canonical: `/u/${encodeURIComponent(profile.username)}` } } : {}),
  };
}

export default async function PublicProfilePage({ params }: Props) {
  const { username } = await params;
  return (
    <Suspense>
      <PublicProfileView username={decodeURIComponent(username)} />
    </Suspense>
  );
}
