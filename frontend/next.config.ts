import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs/config";

function origin(url: string | undefined, fallback: string): string {
  try {
    return new URL(url || fallback).origin;
  } catch {
    return new URL(fallback).origin;
  }
}

/**
 * Where the browser may fetch, XHR or open sockets to. Everything the app
 * calls: its own origin (Next.js), the API, Supabase (auth, storage uploads
 * and realtime), Open-Meteo for trail forecasts, and OpenFreeMap for
 * Explore's map (style, tiles, fonts and sprites, all on one host).
 */
function connectSources(): string {
  const supabase = origin(process.env.NEXT_PUBLIC_SUPABASE_URL, "http://127.0.0.1:44321");
  const sources = [
    "'self'",
    origin(process.env.NEXT_PUBLIC_API_URL, "http://localhost:8000"),
    supabase,
    supabase.replace(/^http/, "ws"),
    "https://api.open-meteo.com",
    "https://tiles.openfreemap.org",
  ];
  // Sentry's ingest host, only once a DSN is set (lib/sentryOptions.ts).
  if (process.env.NEXT_PUBLIC_SENTRY_DSN) sources.push(origin(process.env.NEXT_PUBLIC_SENTRY_DSN, "https://sentry.io"));
  // Vercel's comments toolbar on preview deployments.
  if (process.env.VERCEL_ENV === "preview") sources.push("https://vercel.live", "wss://ws-us3.pusher.com");
  return sources.join(" ");
}

const nextConfig: NextConfig = {
  // Inlined at build time for Sentry (lib/sentryOptions.ts): which
  // deployment this is, and the commit it was built from.
  env: {
    NEXT_PUBLIC_SENTRY_ENVIRONMENT:
      process.env.VERCEL_ENV === "production" ? "production" : process.env.VERCEL_ENV ? "preview" : "local",
    NEXT_PUBLIC_SENTRY_RELEASE: process.env.VERCEL_GIT_COMMIT_SHA ?? "",
  },
  // Lets a second instance (e.g. the local end-to-end stack on another port)
  // run alongside `npm run dev` without sharing build output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  turbopack: {
    root: __dirname,
  },
  async redirects() {
    return [
      // The landing page is served at / only; old links and bookmarks to
      // /landing get a 301 so search engines fold them into /.
      { source: "/landing", destination: "/", statusCode: 301 },
      // Saved trails live on a profile tab now; old links and bookmarks land there.
      { source: "/saved-trails", destination: "/profile?tab=trails", permanent: false },
      // Search lives in Explore's box now. The query string comes along, so
      // /search?tab=hikers&q=ana opens Explore's Hikers tab for "ana".
      { source: "/search", destination: "/trail-list", permanent: true },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // No other site may frame Trekly (clickjacking on account actions),
          // and the browser only talks to the services in connectSources().
          // No script/style policy yet: that needs its own pass over Next's
          // inline scripts.
          { key: "Content-Security-Policy", value: `frame-ancestors 'none'; connect-src ${connectSources()}` },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Location only for Trekly's own pages: Explore's "Use my location".
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(self)" },
          // Only production may be indexed: previews (and local builds) say
          // noindex on every response, as robots.txt and the page metadata do.
          ...(process.env.VERCEL_ENV === "production" ? [] : [{ key: "X-Robots-Tag", value: "noindex, nofollow" }]),
        ],
      },
    ];
  },
};

// Source maps go to Sentry only when SENTRY_AUTH_TOKEN (with SENTRY_ORG and
// SENTRY_PROJECT) is set in Vercel; without it the build skips the upload.
const uploadSourceMaps = Boolean(process.env.SENTRY_AUTH_TOKEN && process.env.SENTRY_ORG && process.env.SENTRY_PROJECT);

export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
  telemetry: false,
  sourcemaps: { disable: !uploadSourceMaps, deleteSourcemapsAfterUpload: true },
  release: { name: process.env.VERCEL_GIT_COMMIT_SHA, create: uploadSourceMaps },
  widenClientFileUpload: uploadSourceMaps,
});
