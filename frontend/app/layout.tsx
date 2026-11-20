import type { Metadata } from "next";
import { Fraunces, DM_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";
import Navbar from "@/components/Navbar";
import PublicProfileNotice from "@/components/PublicProfileNotice";
import SiteFooter from "@/components/SiteFooter";
import RankCelebration from "@/components/RankCelebration";
import MilestoneWatcher from "@/components/MilestoneWatcher";
import VisitStreakWatcher from "@/components/VisitStreakWatcher";
import Toaster from "@/components/Toaster";
import TopoBackground from "@/components/TopoBackground";
import OnboardingGate from "@/components/OnboardingGate";
import PageMemory from "@/components/PageMemory";
import { isIndexable, SITE_NAME, SITE_TITLE, SITE_URL } from "@/lib/site";

// Display/heading font: organic, editorial character that complements the
// hand-drawn Trekly logo. UI/body font: clean and highly readable so the
// interface itself doesn't compete with it. Loaded once here so every page
// inherits the same typography without re-importing fonts per page.
const display = Fraunces({
  subsets: ["latin"],
  weight: ["500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

const sans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
  display: "swap",
});

// Search Console is already verified for the production domain with this
// token; GOOGLE_SITE_VERIFICATION (Vercel env var) overrides it when set.
const GOOGLE_VERIFICATION = process.env.GOOGLE_SITE_VERIFICATION || "eJGo3TdpJRHqJkDda3P2iOGgFzMYuAyD1PL2CKOlvAQ";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    // Every other page sets its own title; this adds the brand: "Privacy Policy | Trekly".
    template: "%s | Trekly",
  },
  description: "Find Canada's best hikes, from day trips to multi-night routes. Check backcountry campsites, plan your trip and pack the right gear.",
  applicationName: SITE_NAME,
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: "en_CA",
    images: [{ url: "/og-default.jpg", width: 1200, height: 630, alt: "An alpine lake below snowy peaks in the Canadian Rockies" }],
  },
  twitter: { card: "summary_large_image", images: ["/og-default.jpg"] },
  // Previews and local builds are never indexed (see lib/site.ts).
  ...(isIndexable() ? {} : { robots: { index: false, follow: false } }),
  verification: { google: GOOGLE_VERIFICATION },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`h-full ${display.variable} ${sans.variable}`}>
      <body className="flex min-h-full flex-col overflow-x-hidden">
        <AuthProvider>
          <Navbar />

          <TopoBackground />
          {/* At least one (small) viewport tall, so the footer credit always
              starts below the first screen and full-height heroes stay full. */}
          <div className="flex min-h-svh flex-1 flex-col">
            <OnboardingGate>{children}</OnboardingGate>
          </div>
          <SiteFooter />
          <PublicProfileNotice />
          <Toaster />
          <RankCelebration />
          <MilestoneWatcher />
          <VisitStreakWatcher />
          <PageMemory />
        </AuthProvider>
      </body>
    </html>
  );
}
