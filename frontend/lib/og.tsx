/**
 * Shared pieces for the social cards (app/opengraph-image.tsx and the trail
 * and profile ones): the 1200x630 size, Trekly's fonts and colours, the
 * brand mark, and photos turned into something the card renderer can draw.
 *
 * next/og renders with Satori, which reads TTF/OTF only (not WOFF2) and
 * can't decode WebP, so the fonts are TTF files in assets/og (OFL, from
 * Google Fonts) and every photo goes through sharp to a JPEG data URL.
 */
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import sharp from "sharp";

export const OG_SIZE = { width: 1200, height: 630 };
/** JPEG, not next/og's PNG: a photo card is ~1.6 MB as PNG and ~150 KB as JPEG (WhatsApp drops previews over ~300 KB). */
export const OG_CONTENT_TYPE = "image/jpeg";

export const OG_COLORS = {
  olive: "#606c38",
  darkOlive: "#283618",
  cream: "#fefae0",
  tan: "#dda15e",
  rust: "#bc6c25",
};

const ASSETS = join(process.cwd(), "assets", "og");

let fontsPromise: Promise<{ name: string; data: Buffer; weight: 500 | 600; style: "normal" }[]> | null = null;

/** Fraunces for headings, DM Sans for everything else; read once per server. */
export function ogFonts() {
  fontsPromise ??= Promise.all([
    readFile(join(ASSETS, "Fraunces-600.ttf")),
    readFile(join(ASSETS, "DMSans-500.ttf")),
    readFile(join(ASSETS, "DMSans-600.ttf")),
  ]).then(([fraunces, sans500, sans600]) => [
    { name: "Fraunces", data: fraunces, weight: 600 as const, style: "normal" as const },
    { name: "DM Sans", data: sans500, weight: 500 as const, style: "normal" as const },
    { name: "DM Sans", data: sans600, weight: 600 as const, style: "normal" as const },
  ]);
  return fontsPromise;
}

function dataUrl(jpeg: Buffer): string {
  return `data:image/jpeg;base64,${jpeg.toString("base64")}`;
}

/** The site's default photo (Lake Agnes), cropped to the card. */
export async function defaultPhoto(): Promise<string> {
  const jpeg = await sharp(await readFile(join(ASSETS, "default-photo.jpg")))
    .resize(OG_SIZE.width, OG_SIZE.height, { fit: "cover" })
    .jpeg({ quality: 82 })
    .toBuffer();
  return dataUrl(jpeg);
}

/**
 * A remote photo (WebP, JPEG or PNG) cropped to width x height, as a JPEG
 * data URL; null when it can't be fetched or decoded, so the card falls
 * back to its plain design instead of failing.
 */
export async function remotePhoto(url: string, width: number, height: number): Promise<string | null> {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!response.ok) return null;
    const jpeg = await sharp(Buffer.from(await response.arrayBuffer()))
      .resize(width, height, { fit: "cover" })
      .jpeg({ quality: 82 })
      .toBuffer();
    return dataUrl(jpeg);
  } catch {
    return null;
  }
}

/**
 * next/og's PNG re-encoded as JPEG. Cards built from live data (trails,
 * profiles) are cached at the CDN for a day, then refreshed in the
 * background, so a new photo or rank shows up without a deploy.
 */
export async function asJpeg(image: Response, { live }: { live: boolean }): Promise<Response> {
  const jpeg = await sharp(Buffer.from(await image.arrayBuffer()))
    .jpeg({ quality: 84, progressive: true, mozjpeg: true })
    .toBuffer();
  return new Response(new Uint8Array(jpeg), {
    headers: {
      "Content-Type": OG_CONTENT_TYPE,
      "Cache-Control": live
        ? "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
        : "public, max-age=31536000, immutable",
    },
  });
}

/** The public URL of an avatar in the avatars bucket (publicly readable). */
export function avatarUrl(path: string): string | null {
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL;
  return base ? `${base.replace(/\/$/, "")}/storage/v1/object/public/avatars/${path}` : null;
}

/** The logo mark (the trail line from app/icon.svg) and the wordmark. */
export function OgBrand({ tone = "light", size = 44 }: { tone?: "light" | "dark"; size?: number }) {
  const ink = tone === "light" ? OG_COLORS.cream : OG_COLORS.darkOlive;
  const tile = tone === "light" ? "rgba(40, 54, 24, 0.78)" : OG_COLORS.darkOlive;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.32 }}>
      <svg width={size} height={size} viewBox="0 0 32 32">
        <rect width="32" height="32" rx="7" fill={tile} />
        <path
          transform="translate(4.6 10.2) scale(0.84)"
          d="M26.6569 0.4C26.5429 0.4 24.4319 0.4 21.2085 0.428503C18.7721 0.450047 16.6998 0.686759 14.3436 0.773995C12.7231 0.833991 11.1132 1.03225 10.278 1.11948C9.49079 1.2017 8.69477 1.37774 8.00292 1.46498C7.23359 1.56199 6.22105 1.78197 5.41173 1.95385C4.69837 2.10535 4.03062 2.41422 3.33877 2.64483C2.64693 2.87545 1.95767 3.1052 1.26582 3.4792C0.937169 3.65686 0.630975 3.79619 0.458228 4.08295C0.364077 4.23924 0.399494 4.48372 0.4565 4.65819C0.68558 5.35931 1.60527 5.6964 2.29711 5.92701C3.13211 6.20535 4.19646 6.21464 5.31844 6.30187C5.58091 6.32228 5.75117 6.38738 7.60647 6.41675C9.46176 6.44611 12.9961 6.44611 14.9024 6.47462C17.5016 6.51348 18.6484 6.73287 19.9725 6.82011C20.8047 6.87494 21.4711 7.36513 22.1629 7.71148C22.5633 7.91193 22.7978 8.28758 22.9705 8.57434C23.3584 9.21828 22.6267 9.72656 22.4549 10.0142C22.0978 10.6117 21.1325 10.6473 20.2973 10.7933C19.5597 10.9222 18.7728 11.1103 18.0222 11.2821C17.3113 11.4449 16.5271 11.7425 15.748 11.8297C14.8934 11.9254 14.1086 12.2607 13.3581 12.6347C12.6662 12.8947 12.148 13.0675 11.8033 13.1823C11.6297 13.2402 11.4587 13.2972 11.2825 13.356"
          fill="none"
          stroke={OG_COLORS.cream}
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span style={{ fontFamily: "Fraunces", fontSize: size * 0.82, color: ink, letterSpacing: -0.5 }}>Trekly</span>
    </div>
  );
}

/** A rounded stat pill: "6.8 km", "380 m gain". */
export function OgStat({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        padding: "14px 24px",
        borderRadius: 18,
        background: "rgba(254, 250, 224, 0.14)",
        border: "1.5px solid rgba(254, 250, 224, 0.32)",
      }}
    >
      <span style={{ fontSize: 20, color: OG_COLORS.tan, fontWeight: 600, textTransform: "uppercase", letterSpacing: 1.5 }}>
        {label}
      </span>
      <span style={{ fontSize: 36, color: OG_COLORS.cream, fontWeight: 600 }}>{value}</span>
    </div>
  );
}
