"use client";

import { useEffect, useState } from "react";
import { signedImageUrl } from "@/lib/storage";
import styles from "./Avatar.module.css";

export function initialsFor(name: string | null | undefined, email: string | null | undefined): string {
  const source = (name ?? "").trim() || (email ?? "").split("@")[0];
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const letters = parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0];
  return letters.toUpperCase();
}

/** The user's uploaded avatar (private bucket, signed URL) or their initials. */
export default function Avatar({
  path,
  name,
  email,
  size = 36,
  preview,
}: {
  path: string | null | undefined;
  name: string | null | undefined;
  email: string | null | undefined;
  size?: number;
  /** Local object URL to show before an upload is saved. */
  preview?: string | null;
}) {
  const [resolved, setResolved] = useState<{ path: string; url: string | null } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    if (!path || preview) return;
    let cancelled = false;
    signedImageUrl("avatars", path).then((url) => !cancelled && setResolved({ path, url }));
    return () => {
      cancelled = true;
    };
  }, [path, preview]);

  const url = preview ?? (path && resolved?.path === path ? resolved.url : null);
  const showImage = Boolean(url) && url !== failed;

  return (
    <span className={styles.avatar} style={{ width: size, height: size, fontSize: size * 0.38 }} aria-hidden="true">
      {showImage ? (
        // Signed, short-lived Storage URLs can't go through next/image.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url!} alt="" className={styles.image} onError={() => setFailed(url)} />
      ) : (
        initialsFor(name, email)
      )}
    </span>
  );
}
