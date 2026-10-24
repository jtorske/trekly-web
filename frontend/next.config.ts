import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets a second instance (e.g. the local end-to-end stack on another port)
  // run alongside `npm run dev` without sharing build output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  turbopack: {
    root: __dirname,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // No other site may frame Trekly (clickjacking on account actions).
          // Only frame-ancestors for now: a full script/style policy needs its
          // own pass over Next's inline scripts and the Supabase endpoints.
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
