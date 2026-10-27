import type { Metadata } from "next";
import { Suspense } from "react";
import type { PublicProfile } from "@/lib/profilesApi";
import { displayName, robotsFor } from "@/lib/publicProfile";
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
  return {
    title: profile ? `${displayName(profile)} (@${profile.username}) · Trekly` : "Profile · Trekly",
    description: profile && !profile.is_private ? profile.bio ?? `${displayName(profile)}'s hikes and gear on Trekly.` : undefined,
    // noindex unless the owner turned on "Let search engines show my profile"
    // (and noindex if the API couldn't be reached to check).
    robots: robotsFor(profile),
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
