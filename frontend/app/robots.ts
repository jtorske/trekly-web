import type { MetadataRoute } from "next";
import { absoluteUrl, isIndexable } from "@/lib/site";

/** Signed-in, personal and auth pages: nothing there for search engines. */
const PRIVATE_PATHS = [
  "/admin",
  "/settings",
  "/profile",
  "/welcome",
  "/auth",
  "/api/",
  "/activity",
  "/alerts",
  "/gear",
  "/journal",
  "/notifications",
  "/plans",
  "/saved-trails",
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
];

export default function robots(): MetadataRoute.Robots {
  // Vercel previews (and local builds) are kept out of search entirely.
  if (!isIndexable()) return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: { userAgent: "*", allow: "/", disallow: PRIVATE_PATHS },
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
