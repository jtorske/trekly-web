import { ImageResponse } from "next/og";
import { asJpeg, avatarUrl, OG_COLORS, OG_CONTENT_TYPE, OG_SIZE, OgBrand, ogFonts, remotePhoto } from "@/lib/og";
import type { PublicProfile } from "@/lib/profilesApi";
import { province } from "@/lib/provinces";
import { displayName } from "@/lib/publicProfile";

// The card a shared profile link shows. It reads the signed-out visitor view,
// so it never shows more than a stranger opening the link would see: a
// private profile is its name, avatar and "Private profile", nothing else.
export const alt = "A Trekly hiker's profile card";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const AVATAR = 232;

type Props = { params: Promise<{ username: string }> };

async function fetchProfile(username: string): Promise<PublicProfile | null> {
  try {
    const response = await fetch(`${API_BASE}/api/profiles/${encodeURIComponent(username)}`, {
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(6000),
    });
    return response.ok ? ((await response.json()) as PublicProfile) : null;
  } catch {
    return null;
  }
}

function count(n: number, one: string, many: string): string {
  return `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
}

export default async function Image({ params }: Props) {
  const { username } = await params;
  const [profile, fonts] = await Promise.all([fetchProfile(decodeURIComponent(username)), ogFonts()]);
  const avatarSource = profile?.avatar_path ? avatarUrl(profile.avatar_path) : null;
  const avatar = avatarSource ? await remotePhoto(avatarSource, AVATAR * 2, AVATAR * 2) : null;

  const name = profile ? displayName(profile) : "A Trekly hiker";
  const initial = (profile?.display_name?.trim() || profile?.username || "T").charAt(0).toUpperCase();
  const home = profile ? province(profile.home_province) : null;
  const chips = profile && !profile.is_private
    ? [profile.rank?.title, home ? home.name : null].filter((chip): chip is string => Boolean(chip))
    : [];
  const hikes = profile?.journal?.entries.length ?? null;
  const stats = profile && !profile.is_private
    ? [
        // Zeros are left out: "0 followers" isn't worth putting on a card.
        hikes ? count(hikes, "hike", "hikes") : null,
        profile.followers_count ? count(profile.followers_count, "follower", "followers") : null,
        profile.following_count ? `${profile.following_count.toLocaleString("en-US")} following` : null,
      ].filter((stat): stat is string => Boolean(stat))
    : [];

  const image = new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "56px 72px",
          fontFamily: "DM Sans",
          background: `linear-gradient(135deg, ${OG_COLORS.cream} 0%, #f3ecc8 100%)`,
          color: OG_COLORS.darkOlive,
          borderBottom: `18px solid ${OG_COLORS.olive}`,
        }}
      >
        <OgBrand tone="dark" size={46} />
        <div style={{ display: "flex", alignItems: "center", gap: 56 }}>
          {avatar ? (
            // eslint-disable-next-line @next/next/no-img-element -- next/og draws plain img elements
            <img
              src={avatar}
              alt=""
              width={AVATAR}
              height={AVATAR}
              style={{ borderRadius: AVATAR, border: `6px solid ${OG_COLORS.olive}` }}
            />
          ) : (
            <div
              style={{
                width: AVATAR,
                height: AVATAR,
                borderRadius: AVATAR,
                background: OG_COLORS.olive,
                color: OG_COLORS.cream,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: "Fraunces",
                fontSize: 110,
              }}
            >
              {initial}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", maxWidth: 740 }}>
            <span style={{ fontFamily: "Fraunces", fontSize: name.length > 22 ? 58 : 72, lineHeight: 1.05, letterSpacing: -1 }}>
              {name}
            </span>
            {profile && (
              <span style={{ fontSize: 30, marginTop: 8, color: OG_COLORS.olive, fontWeight: 600 }}>@{profile.username}</span>
            )}
            {profile?.is_private ? (
              <span style={{ fontSize: 28, marginTop: 24, color: "rgba(40,54,24,0.72)" }}>Private profile</span>
            ) : (
              <div style={{ display: "flex", flexDirection: "column" }}>
                {chips.length > 0 && (
                  <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
                    {chips.map((chip) => (
                      <span
                        key={chip}
                        style={{
                          fontSize: 24,
                          fontWeight: 600,
                          padding: "8px 20px",
                          borderRadius: 999,
                          background: OG_COLORS.darkOlive,
                          color: OG_COLORS.cream,
                        }}
                      >
                        {chip}
                      </span>
                    ))}
                  </div>
                )}
                {stats.length > 0 && (
                  <span style={{ fontSize: 28, marginTop: 22, color: "rgba(40,54,24,0.8)" }}>{stats.join("  ·  ")}</span>
                )}
              </div>
            )}
          </div>
        </div>
        <span style={{ fontSize: 24, color: "rgba(40,54,24,0.66)" }}>Hikes, gear and trail journal on Trekly</span>
      </div>
    ),
    { ...size, fonts },
  );
  return asJpeg(image, { live: true });
}
