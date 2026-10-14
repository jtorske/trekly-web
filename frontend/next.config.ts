import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets a second instance (e.g. the local end-to-end stack on another port)
  // run alongside `npm run dev` without sharing build output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
