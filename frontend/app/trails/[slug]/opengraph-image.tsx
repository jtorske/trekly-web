import { ImageResponse } from "next/og";
import { PROVINCE_NAMES } from "@/lib/exploreFilters";
import { asJpeg, OG_COLORS, OG_CONTENT_TYPE, OG_SIZE, OgBrand, OgStat, ogFonts, remotePhoto } from "@/lib/og";
import { TERRAIN_LABELS } from "@/lib/terrain";
import { trailImage, trailPlace } from "@/lib/trailSeo";
import { getTrailBySlug } from "@/lib/trailsServer";
import { formatDistance, formatElevation } from "@/lib/units";

// The card a shared trail link shows: its photo, name, place and numbers.
// Metric, like the page's search description (a card is the same for everyone).
export const alt = "Trail photo with its name, distance and elevation gain on Trekly";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

type Props = { params: Promise<{ slug: string }> };

/** Smaller type for long names, so they stay on two lines. */
function nameSize(name: string): number {
  if (name.length > 48) return 52;
  if (name.length > 30) return 62;
  return 74;
}

export default async function Image({ params }: Props) {
  const { slug } = await params;
  const [trail, fonts] = await Promise.all([
    getTrailBySlug(decodeURIComponent(slug)).catch(() => null),
    ogFonts(),
  ]);
  const source = trail ? trailImage(trail) : null;
  const photo = source ? await remotePhoto(source.url, OG_SIZE.width, OG_SIZE.height) : null;

  const province = trail?.province_code ? PROVINCE_NAMES[trail.province_code] : null;
  const place = trail ? [trailPlace(trail), province].filter((part, i, all) => part && all.indexOf(part) === i).join(" · ") : "";
  const nights = trail?.typical_duration_nights ?? 0;
  const stats = trail
    ? [
        trail.distance_km ? { label: "Distance", value: formatDistance(Number(trail.distance_km), "metric") } : null,
        trail.elevation_gain_m ? { label: "Elevation gain", value: formatElevation(trail.elevation_gain_m, "metric") } : null,
        { label: "Trip", value: nights > 0 ? `${nights} night${nights === 1 ? "" : "s"}` : "Day hike" },
        { label: "Difficulty", value: TERRAIN_LABELS[trail.terrain] },
      ].filter((stat): stat is { label: string; value: string } => stat !== null)
    : [];

  const image = new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          position: "relative",
          fontFamily: "DM Sans",
          background: OG_COLORS.darkOlive,
        }}
      >
        {photo && (
          // eslint-disable-next-line @next/next/no-img-element -- next/og draws plain img elements
          <img src={photo} alt="" width={OG_SIZE.width} height={OG_SIZE.height} style={{ position: "absolute", top: 0, left: 0 }} />
        )}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: photo
              ? "linear-gradient(180deg, rgba(40,54,24,0.6) 0%, rgba(40,54,24,0) 24%, rgba(40,54,24,0.5) 44%, rgba(40,54,24,0.88) 62%, rgba(40,54,24,0.96) 100%)"
              : `linear-gradient(160deg, ${OG_COLORS.olive} 0%, ${OG_COLORS.darkOlive} 70%)`,
          }}
        />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "52px 64px", width: "100%" }}>
          <OgBrand size={46} />
          {trail ? (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {place && (
                <span style={{ fontSize: 28, fontWeight: 600, color: OG_COLORS.tan, marginBottom: 8, textShadow: "0 1px 8px rgba(0,0,0,0.5)" }}>
                  {place}
                </span>
              )}
              <span
                style={{
                  fontFamily: "Fraunces",
                  fontSize: nameSize(trail.name),
                  lineHeight: 1.05,
                  color: OG_COLORS.cream,
                  letterSpacing: -1,
                  maxWidth: 1050,
                }}
              >
                {trail.name}
              </span>
              <div style={{ display: "flex", gap: 16, marginTop: 28 }}>
                {stats.map((stat) => (
                  <OgStat key={stat.label} label={stat.label} value={stat.value} />
                ))}
              </div>
            </div>
          ) : (
            <span style={{ fontFamily: "Fraunces", fontSize: 72, color: OG_COLORS.cream }}>Find your next hike</span>
          )}
        </div>
      </div>
    ),
    { ...size, fonts },
  );
  return asJpeg(image, { live: true });
}
