import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { FooterNotice } from "@/components/SiteFooter";
import {
  LANDING_PHOTOS,
  LANDING_PHOTO_COOKIE,
  pickLandingPhoto,
} from "@/lib/landingPhotos";
import { FEATURED_DEMO, demoProfileHref } from "@/lib/demo";
import { absoluteUrl, SITE_NAME, SITE_URL } from "@/lib/site";
import { jsonLdScript } from "@/lib/trailSeo";
import HeroCarousel from "./HeroCarousel";
import TrailSearch from "./TrailSearch";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: { absolute: "Trekly: Canadian day hikes and backcountry trips" },
  // Served at both / and /landing; / is the one to index.
  alternates: { canonical: "/" },
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
      url: absoluteUrl("/"),
      logo: absoluteUrl("/apple-icon.png"),
      description: "Canadian day hikes and backcountry trips: trails, campsites, trip plans and gear.",
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      name: SITE_NAME,
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
  const photo = pickLandingPhoto(LANDING_PHOTOS, lastSrc);
  const start = LANDING_PHOTOS.indexOf(photo);
  const showDemo = await demoProfileExists();

  return (
    <main className={styles.hero}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(SITE_JSON_LD) }} />
      <HeroCarousel photos={LANDING_PHOTOS} start={start}>
        <div aria-hidden="true" className={styles.scrim} />

        <section className={styles.section}>
          <div className={styles.content}>
            <h1 className={styles.headline}>Your next trail is waiting</h1>

            <p className={styles.subtext}>
              Find Canada&apos;s best hikes, from day trips to multi-night routes.
              Check backcountry campsites, plan your trip and pack the right&nbsp;gear.
            </p>

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
