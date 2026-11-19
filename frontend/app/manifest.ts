import type { MetadataRoute } from "next";
import { SITE_NAME, SITE_TITLE } from "@/lib/site";

/** Name and icons for "Add to Home Screen", matching the favicon and logo. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE_TITLE,
    short_name: SITE_NAME,
    description: "Find Canada's best hikes, check backcountry campsites, plan your trip and pack the right gear.",
    start_url: "/",
    display: "standalone",
    background_color: "#fefae0",
    theme_color: "#283618",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
