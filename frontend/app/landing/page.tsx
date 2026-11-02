import type { Metadata } from "next";
import Image from "next/image";
import { cookies } from "next/headers";
import { FooterNotice } from "@/components/SiteFooter";
import {
  LANDING_PHOTOS,
  LANDING_PHOTO_COOKIE,
  pickLandingPhoto,
} from "@/lib/landingPhotos";
import RememberPhoto from "./RememberPhoto";
import TrailSearch from "./TrailSearch";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Trekly: Canadian day hikes and backcountry trips",
  description:
    "Find Canada's best hikes, from day trips to multi-night routes. Check backcountry campsites, plan your trip and pack the right gear.",
};

export default async function LandingPage() {
  // Picked per request (reading the cookie makes the page dynamic), so the
  // first paint already shows this visit's photo: no client-side swap.
  const lastSrc = (await cookies()).get(LANDING_PHOTO_COOKIE)?.value;
  const photo = pickLandingPhoto(LANDING_PHOTOS, lastSrc);

  return (
    <main className={styles.hero}>
      <div className={styles.backdropContainer}>
        <Image
          src={photo.src}
          alt=""
          aria-hidden="true"
          fill
          preload
          sizes="100vw"
          className={styles.backdrop}
          style={photo.position ? { objectPosition: photo.position } : undefined}
        />
      </div>
      <RememberPhoto src={photo.src} />

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

      {photo.credit && (
        <p className={styles.credit}>
          {photo.credit.href ? (
            <a href={photo.credit.href} target="_blank" rel="noopener noreferrer">
              {photo.credit.text}
            </a>
          ) : (
            photo.credit.text
          )}
        </p>
      )}
    </main>
  );
}
