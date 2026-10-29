import type { NextConfig } from "next";

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
 * and realtime) and Open-Meteo for trail forecasts.
 */
function connectSources(): string {
  const supabase = origin(process.env.NEXT_PUBLIC_SUPABASE_URL, "http://127.0.0.1:44321");
  const sources = [
    "'self'",
    origin(process.env.NEXT_PUBLIC_API_URL, "http://localhost:8000"),
    supabase,
    supabase.replace(/^http/, "ws"),
    "https://api.open-meteo.com",
  ];
  // Vercel's comments toolbar on preview deployments.
  if (process.env.VERCEL_ENV === "preview") sources.push("https://vercel.live", "wss://ws-us3.pusher.com");
  return sources.join(" ");
}

const nextConfig: NextConfig = {
  // Lets a second instance (e.g. the local end-to-end stack on another port)
  // run alongside `npm run dev` without sharing build output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  turbopack: {
    root: __dirname,
  },
  async redirects() {
    return [
      // Saved trails live on a profile tab now; old links and bookmarks land there.
      { source: "/saved-trails", destination: "/profile?tab=trails", permanent: false },
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
        ],
      },
    ];
  },
};

export default nextConfig;
