import type { Metadata } from "next";

// The landing page is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: "Trekly: Canadian day hikes and backcountry trips",
  description:
    "Find Canada's best hikes, from day trips to multi-night routes. Check backcountry campsites, plan your trip and pack the right gear.",
};

export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
