"use client";

import { useState, type CSSProperties } from "react";
import { DEFAULT_TOPO_MAP, TOPO_MAPS } from "@/lib/topoMaps";
import { photoCredit } from "@/lib/trailPhoto";
import type { TrailPhoto as Photo } from "@/lib/trailsApi";
import styles from "./TrailPhoto.module.css";

const TOPO_STYLE = { "--topo-map": `url(${TOPO_MAPS[DEFAULT_TOPO_MAP].src})` } as CSSProperties;

/**
 * A trail's approved photo, or the topo fallback (contour lines and the
 * trail name) when it has none or the image fails to load, so a trail never
 * shows a broken image. `hero` is the trail page banner; `thumb` fills a
 * card. The credit line is a separate component because on cards it has to
 * sit outside the card's link.
 */
export default function TrailPhoto({
  photo,
  name,
  variant,
}: {
  photo: Photo | null | undefined;
  name: string;
  variant: "hero" | "thumb";
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const url = photo ? (variant === "hero" ? photo.hero_url : photo.thumb_url) : null;
  const showPhoto = url !== null && failedUrl !== url;

  return (
    <div className={`${styles.frame} ${styles[variant]}`}>
      {showPhoto ? (
        // Plain <img>: the files are already resized WebP on Storage's CDN.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className={styles.image}
          src={url}
          alt=""
          width={photo!.width}
          height={photo!.height}
          loading={variant === "hero" ? "eager" : "lazy"}
          fetchPriority={variant === "hero" ? "high" : "auto"}
          decoding="async"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <div className={styles.fallback} style={TOPO_STYLE} aria-hidden="true">
          <div className={styles.contours} />
          <span className={styles.fallbackName}>{name}</span>
        </div>
      )}
    </div>
  );
}

export function PhotoCredit({ photo, className }: { photo: Photo | null | undefined; className?: string }) {
  if (!photo) return null;
  const credit = photoCredit(photo);
  const classes = `${styles.credit} ${className ?? ""}`;
  return credit.href ? (
    <a className={classes} href={credit.href} title={credit.title ?? undefined} target="_blank" rel="noopener noreferrer">
      {credit.text}
    </a>
  ) : (
    <span className={classes}>{credit.text}</span>
  );
}
