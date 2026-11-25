"use client";

import Image from "next/image";
import { useState } from "react";
import { publicAvatarUrl } from "@/lib/storage";
import styles from "./Avatar.module.css";

export function initialsFor(name: string | null | undefined, email: string | null | undefined): string {
  const source = (name ?? "").trim() || (email ?? "").split("@")[0];
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const letters = parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0];
  return letters.toUpperCase();
}

/**
 * The user's uploaded avatar (public bucket) or their initials. Every photo
 * change saves to a new path, so the URL changes and no cache can serve the
 * old photo. Decorative unless `alt` is given.
 */
export default function Avatar({
  path,
  name,
  email,
  size = 36,
  preview,
  alt,
}: {
  path: string | null | undefined;
  name: string | null | undefined;
  email: string | null | undefined;
  size?: number;
  /** Local object URL to show before an upload is saved. */
  preview?: string | null;
  /** e.g. "Jordan's profile photo"; omit where the avatar is decorative. */
  alt?: string;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const url = preview ?? (path ? publicAvatarUrl(path) : null);
  const showImage = Boolean(url) && url !== failed;
  const label = alt && !showImage ? { role: "img", "aria-label": alt } : {};

  return (
    <span
      className={styles.avatar}
      data-avatar
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden={alt ? undefined : true}
      {...label}
    >
      {showImage ? (
        // Stored avatars are 512 px; next/image sends one sized for this
        // spot (1x/2x of `size`) as AVIF/WebP. Local previews are blob: URLs
        // the optimizer can't fetch, so they're shown as they are. Lazy:
        // avatars shouldn't compete with a page's main photo.
        <Image
          src={url!}
          alt={alt ?? ""}
          className={styles.image}
          width={size}
          height={size}
          unoptimized={Boolean(preview)}
          onError={() => setFailed(url)}
        />
      ) : (
        initialsFor(name, email)
      )}
    </span>
  );
}
