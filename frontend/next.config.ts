import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets a second instance (e.g. the local end-to-end stack on another port)
  // run alongside `npm run dev` without sharing build output.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The app is self-contained in frontend/. Vercel defaults the tracing root
  // to the repo root (NEXT_PRIVATE_OUTPUT_TRACE_ROOT), and Next.js then
  // overrides turbopack.root with it, which breaks next/font resolution.
  // Setting both to this directory keeps them in step.
  outputFileTracingRoot: __dirname,
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
