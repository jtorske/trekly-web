import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { FooterNotice } from "@/components/SiteFooter";
import { LANDING_PHOTO_COOKIE, landingPhotosFor, pickLandingPhoto } from "@/lib/landingPhotos";
import { getSeasonOnServer } from "@/lib/trailsServer";
import { FEATURED_DEMO, demoProfileHref } from "@/lib/demo";
import {
  absoluteUrl,
  OFFICIAL_PROFILES,
  SITE_ALTERNATE_NAME,
  SITE_NAME,
  SITE_TITLE,
  SITE_URL,
} from "@/lib/site";
import { jsonLdScript } from "@/lib/trailSeo";
import HeroCarousel from "./HeroCarousel";
import TrailSearch from "./TrailSearch";
import styles from "./page.module.css";

export const metadata: Metadata = {
  // Brand first, so searches for "Trekly" match it at a glance.
  title: { absolute: SITE_TITLE },
  alternates: { canonical: absoluteUrl("/") },
  description:
    "Find Canada's best hikes, from day trips to multi-night routes. Check backcountry campsites, plan your trip and pack the right gear.",
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Whether the demo profile is there to link to; cached for ten minutes, false on any failure. */
async function demoProfileExists(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/profiles/${FEATURED_DEMO}`, {
      next: { revalidate: 600 },
      signal: AbortSignal.timeout(1500),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/** schema.org Organization + WebSite (with the Explore search as its SearchAction). */
const SITE_JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: SITE_NAME,
      alternateName: SITE_ALTERNATE_NAME,
      url: absoluteUrl("/"),
      logo: absoluteUrl("/apple-icon.png"),
      ...(OFFICIAL_PROFILES.length ? { sameAs: OFFICIAL_PROFILES } : {}),
      description: "Canadian day hikes and backcountry trips: trails, campsites, trip plans and gear.",
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      name: SITE_NAME,
      alternateName: SITE_ALTERNATE_NAME,
      url: absoluteUrl("/"),
      inLanguage: "en-CA",
      publisher: { "@id": `${SITE_URL}/#organization` },
      potentialAction: {
        "@type": "SearchAction",
        target: { "@type": "EntryPoint", urlTemplate: `${absoluteUrl("/trail-list")}?q={search_term_string}` },
        "query-input": "required name=search_term_string",
      },
    },
  ],
};

export default async function LandingPage() {
  // Picked per request (reading the cookie makes the page dynamic), so the
  // first paint already shows this visit's photo: no client-side swap. The
  // carousel then rotates through the rest of the pool from there.
  const lastSrc = (await cookies()).get(LANDING_PHOTO_COOKIE)?.value;
  // Winter photos and words from Nov 15 to Apr 15 (app/season.py).
  const [season, showDemo] = await Promise.all([getSeasonOnServer(), demoProfileExists()]);
  const winter = season === "winter";
  const photos = landingPhotosFor(season);
  const photo = pickLandingPhoto(photos, lastSrc);
  const start = photos.indexOf(photo);

  return (
    <main className={styles.hero}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(SITE_JSON_LD) }} />
      <HeroCarousel photos={photos} start={start}>
        <div aria-hidden="true" className={styles.scrim} />

        <section className={styles.section}>
          <div className={styles.content}>
            <h1 className={styles.headline}>
              {winter ? "Winter trails are waiting" : "Your next trail is waiting"}
            </h1>

            {winter ? (
              <p className={styles.subtext}>
                Snowshoe routes, winter walks and groomed ski trails from the parks&apos; own winter lists.
                Check conditions and pack the right&nbsp;gear.
              </p>
            ) : (
              <p className={styles.subtext}>
                Trekly finds Canada&apos;s best hikes, from day trips to multi-night routes.
                Check backcountry campsites, plan your trip and pack the right&nbsp;gear.
              </p>
            )}

            <TrailSearch />

            {showDemo && (
              <p className={styles.demo}>
                Just looking?{" "}
                <Link href={demoProfileHref} className={styles.demoLink}>
                  See a demo profile
                  <ArrowRight size={15} aria-hidden="true" />
                </Link>
              </p>
            )}
          </div>
        </section>

        <FooterNotice className={styles.footer} />
      </HeroCarousel>
    </main>
  );
}
