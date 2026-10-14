"use client";

import { useEffect, useState } from "react";
import { GearIcon, type IconKey } from "@/app/gear/icons";
import type { ProductImage } from "@/lib/gearApi";
import { signedImageUrl } from "@/lib/storage";
import styles from "./GearThumb.module.css";

/**
 * Product or user photo with a consistent illustrated fallback. Images are
 * contained (never cropped) inside a fixed square, and any load failure falls
 * back to the category illustration instead of a broken image.
 */
export default function GearThumb({
  icon,
  productImage,
  photoPath,
  alt,
  size = "md",
}: {
  icon: IconKey;
  productImage?: ProductImage | null;
  photoPath?: string | null;
  alt: string;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const [photo, setPhoto] = useState<{ path: string; url: string | null } | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!photoPath) return;
    let cancelled = false;
    signedImageUrl("gear-photos", photoPath)
      .then((url) => !cancelled && setPhoto({ path: photoPath, url }))
      .catch(() => !cancelled && setPhoto({ path: photoPath, url: null }));
    return () => {
      cancelled = true;
    };
  }, [photoPath]);

  const photoUrl = photoPath && photo?.path === photoPath ? photo.url : null;
  const url = photoUrl ?? productImage?.url ?? null;
  const showImage = url !== null && url !== failedUrl;

  return (
    <span className={`${styles.thumb} ${styles[size]}`}>
      {showImage ? (
        // Remote catalogue images come from many licensed hosts and user
        // photos from signed Storage URLs, so next/image's fixed remote
        // allow-list doesn't fit; sizes are bounded by CSS instead.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={alt}
          className={styles.image}
          loading="lazy"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <GearIcon icon={icon} className={styles.icon} />
      )}
    </span>
  );
}
