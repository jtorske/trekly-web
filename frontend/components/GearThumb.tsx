"use client";

import { useEffect, useState } from "react";
import { GearIcon, type IconKey } from "@/app/gear/icons";
import type { ProductImage } from "@/lib/gearApi";
import { thumbImageUrl } from "@/lib/gearImage";
import { signedImageUrl } from "@/lib/storage";
import styles from "./GearThumb.module.css";

/**
 * Catalogue photo with a consistent illustrated fallback. Images are
 * contained (never cropped) inside a fixed square, and any load failure falls
 * back to the category illustration instead of a broken image.
 *
 * `ownPhotoPath` is the owner's own upload. Only the item's detail view
 * passes it: lists, setups, the mat and public profiles show the catalogue
 * photo or the icon, never a user photo (lib/gearImage.ts).
 */
export default function GearThumb({
  icon,
  productImage,
  ownPhotoPath,
  alt,
  size = "md",
}: {
  icon: IconKey;
  productImage?: ProductImage | null;
  ownPhotoPath?: string | null;
  alt: string;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const [photo, setPhoto] = useState<{ path: string; url: string | null } | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!ownPhotoPath) return;
    let cancelled = false;
    signedImageUrl("gear-photos", ownPhotoPath)
      .then((url) => !cancelled && setPhoto({ path: ownPhotoPath, url }))
      .catch(() => !cancelled && setPhoto({ path: ownPhotoPath, url: null }));
    return () => {
      cancelled = true;
    };
  }, [ownPhotoPath]);

  const photoUrl = ownPhotoPath && photo?.path === ownPhotoPath ? photo.url : null;
  const url = thumbImageUrl(productImage, photoUrl);
  const showImage = url !== null && url !== failedUrl;

  return (
    <span className={`${styles.thumb} ${styles[size]}`}>
      {showImage ? (
        // Remote catalogue images come from many licensed hosts and the
        // owner's photo from a signed Storage URL, so next/image's fixed remote
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
