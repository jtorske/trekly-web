"use client";

import { useState, type CSSProperties } from "react";
import { DEFAULT_TOPO_MAP, TOPO_MAPS } from "@/lib/topoMaps";
import { photoCredit, ROUTE_MAP_CREDIT, trailImageAlt } from "@/lib/trailPhoto";
import type { TrailPhoto as Photo, TrailRouteMap } from "@/lib/trailsApi";
import styles from "./TrailPhoto.module.css";

const TOPO_STYLE = { "--topo-map": `url(${TOPO_MAPS[DEFAULT_TOPO_MAP].src})` } as CSSProperties;

/**
 * A trail's approved photo; without one, its route map (the stored route on
 * the topo style); without either, the topo fallback (contour lines). The
 * trail name is written over both fallbacks. Each falls through to the next
 * if its image fails to load, so a trail never shows a broken image.
 * `hero` is the trail page banner; `thumb` fills a card. The credit line is
 * a separate component because on cards it has to sit outside the card's link.
 */
export default function TrailPhoto({
  photo,
  routeMap,
  name,
  variant,
  mini = false,
  priority = false,
}: {
  photo: Photo | null | undefined;
  routeMap?: TrailRouteMap | null;
  name: string;
  variant: "hero" | "thumb";
  /** A very small thumb: the fallbacks leave out the trail name, which wouldn't fit. */
  mini?: boolean;
  /** Above the fold on first paint (Explore's first cards): load now, at high priority. */
  priority?: boolean;
}) {
  const [failed, setFailed] = useState<readonly string[]>([]);
  const pick = (image: Photo | TrailRouteMap | null | undefined) =>
    image ? (variant === "hero" ? image.hero_url : image.thumb_url) : null;
  const photoUrl = pick(photo);
  const mapUrl = pick(routeMap);
  const shown =
    photo && photoUrl && !failed.includes(photoUrl)
      ? { url: photoUrl, image: photo, kind: "photo" as const }
      : routeMap && mapUrl && !failed.includes(mapUrl)
        ? { url: mapUrl, image: routeMap, kind: "map" as const }
        : null;

  return (
    <div className={`${styles.frame} ${styles[variant]}`}>
      {shown ? (
        <>
          {/* Plain <img>: the files are already resized WebP on Storage's CDN. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            key={shown.url}
            className={styles.image}
            src={shown.url}
            {...heroSources(variant, shown.kind === "photo" ? photo : null)}
            alt={trailImageAlt(name, shown.kind, shown.kind === "photo" ? photo?.scope : null)}
            width={shown.image.width}
            height={shown.image.height}
            loading={variant === "hero" || priority ? "eager" : "lazy"}
            fetchPriority={variant === "hero" || priority ? "high" : "auto"}
            decoding="async"
            onError={() => setFailed((list) => [...list, shown.url])}
          />
          {shown.kind === "map" && (
            <div className={`${styles.fallback} ${styles.mapLabel}`} aria-hidden="true">
              {!mini && <span className={styles.fallbackName}>{name}</span>}
            </div>
          )}
        </>
      ) : (
        <div className={styles.fallback} style={TOPO_STYLE} aria-hidden="true">
          <div className={styles.contours} />
          {!mini && <span className={styles.fallbackName}>{name}</span>}
        </div>
      )}
    </div>
  );
}

/**
 * The trail page hero's srcset: the ~1000 px rendition for phones, the
 * 1600 px hero for wider or denser screens. The hero spans the page up to
 * 48rem (app/trails/page.module.css .wrap). Nothing for thumbs, route maps
 * or photos without a medium file, which keep the plain src.
 */
export function heroSources(
  variant: "hero" | "thumb",
  photo: Pick<Photo, "hero_url" | "medium_url" | "width"> | null | undefined,
): { srcSet?: string; sizes?: string } {
  if (variant !== "hero" || !photo?.medium_url) return {};
  return {
    srcSet: `${photo.medium_url} 1000w, ${photo.hero_url} ${photo.width}w`,
    sizes: "(max-width: 48rem) 100vw, 48rem",
  };
}

/**
 * The photo's credit; `place` (the park, or the region) is named for a photo
 * of the park rather than the trail. With no photo but a route map, the
 * map's data credit (pass `routeMap`).
 */
export function PhotoCredit({
  photo,
  routeMap,
  place,
  className,
}: {
  photo: Photo | null | undefined;
  routeMap?: TrailRouteMap | null;
  place?: string | null;
  className?: string;
}) {
  const credit = photo ? photoCredit(photo, place) : routeMap ? ROUTE_MAP_CREDIT : null;
  if (!credit) return null;
  const classes = `${styles.credit} ${className ?? ""}`;
  return credit.href ? (
    <a className={classes} href={credit.href} title={credit.title ?? undefined} target="_blank" rel="noopener noreferrer">
      {credit.text}
    </a>
  ) : (
    <span className={classes}>{credit.text}</span>
  );
}
