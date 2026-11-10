import type { Metadata } from "next";
import { cookies } from "next/headers";
import { FooterNotice } from "@/components/SiteFooter";
import {
  LANDING_PHOTOS,
  LANDING_PHOTO_COOKIE,
  pickLandingPhoto,
} from "@/lib/landingPhotos";
import HeroCarousel from "./HeroCarousel";
import TrailSearch from "./TrailSearch";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Trekly: Canadian day hikes and backcountry trips",
  description:
    "Find Canada's best hikes, from day trips to multi-night routes. Check backcountry campsites, plan your trip and pack the right gear.",
};

export default async function LandingPage() {
  // Picked per request (reading the cookie makes the page dynamic), so the
  // first paint already shows this visit's photo: no client-side swap. The
  // carousel then rotates through the rest of the pool from there.
  const lastSrc = (await cookies()).get(LANDING_PHOTO_COOKIE)?.value;
  const photo = pickLandingPhoto(LANDING_PHOTOS, lastSrc);
  const start = LANDING_PHOTOS.indexOf(photo);

  return (
    <main className={styles.hero}>
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
          </div>
        </section>

        <FooterNotice className={styles.footer} />
      </HeroCarousel>
    </main>
  );
}
