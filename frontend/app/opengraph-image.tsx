import { ImageResponse } from "next/og";
import { asJpeg, defaultPhoto, OG_COLORS, OG_CONTENT_TYPE, OG_SIZE, OgBrand, ogFonts } from "@/lib/og";

// The site's default social card: every page without its own (trail pages
// and profiles have theirs). Built once at build time.
export const alt = "Trekly: an alpine lake below snowy peaks in the Canadian Rockies";
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default async function Image() {
  const [photo, fonts] = await Promise.all([defaultPhoto(), ogFonts()]);
  const image = new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", position: "relative", fontFamily: "DM Sans" }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- next/og draws plain img elements */}
        <img src={photo} alt="" width={OG_SIZE.width} height={OG_SIZE.height} style={{ position: "absolute", top: 0, left: 0 }} />
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background:
              "linear-gradient(90deg, rgba(40,54,24,0.95) 0%, rgba(40,54,24,0.86) 42%, rgba(40,54,24,0.35) 68%, rgba(40,54,24,0) 85%)",
          }}
        />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "64px 72px", width: "100%" }}>
          <OgBrand size={56} />
          <div style={{ display: "flex", flexDirection: "column", maxWidth: 680 }}>
            <span style={{ fontFamily: "Fraunces", fontSize: 76, lineHeight: 1.05, color: OG_COLORS.cream, letterSpacing: -1 }}>
              Plan your next Canadian hike
            </span>
            <span style={{ marginTop: 24, fontSize: 30, lineHeight: 1.35, color: OG_COLORS.cream, textShadow: "0 2px 12px rgba(0,0,0,0.45)" }}>
              Trails, backcountry campsites, weather and gear, all in one place.
            </span>
          </div>
        </div>
      </div>
    ),
    { ...size, fonts },
  );
  return asJpeg(image, { live: false });
}
