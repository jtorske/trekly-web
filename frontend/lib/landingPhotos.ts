/**
 * The landing hero's photo pool. Each visit shows one of these, picked on the
 * server, and never the same one twice in a row for a returning visitor.
 *
 * To add a photo, drop it in public/images and list it here. Photos that
 * aren't Jordan's own (e.g. from Wikimedia Commons) need a `credit`, which
 * shows in small text in the hero's corner.
 */
export interface LandingPhoto {
  /** Path under public/. Also what the "last photo" cookie stores. */
  src: string;
  /** CSS object-position, when the default crop hides the subject. */
  position?: string;
  credit?: { text: string; href?: string };
}

export const LANDING_PHOTOS: LandingPhoto[] = [
  { src: "/images/IMG_9031.jpeg" },
  { src: "/images/IMG_8988.jpeg" },
  { src: "/images/IMG_8873.jpeg" },
  { src: "/images/IMG_9332.jpeg" },
  { src: "/images/IMG_9336.jpeg" },
];

/**
 * Winter's pool (Nov 15 - Apr 15, by app/season.py through GET /api/season).
 * Wikimedia Commons photos under Creative Commons licences, resized and
 * re-encoded as WebP; each credits its author and licence and links to the
 * file page.
 */
export const WINTER_LANDING_PHOTOS: LandingPhoto[] = [
  {
    src: "/images/winter-emerald-lake-dusk.webp",
    credit: {
      text: "Emerald Lake, Yoho: JLRPHOTO, CC BY-SA 4.0",
      href: "https://commons.wikimedia.org/wiki/File:Emerald_Lake_Yoho_Winter_BC.jpg",
    },
  },
  {
    src: "/images/winter-lake-louise.webp",
    credit: {
      text: "Lake Louise in winter: Jack Borno, CC BY-SA 3.0",
      href: "https://commons.wikimedia.org/wiki/File:Lake_Louise_Winter_-_panoramio.jpg",
    },
  },
  {
    src: "/images/winter-emerald-lake-ice.webp",
    position: "center 65%",
    credit: {
      text: "Emerald Lake in winter: Natulive Canada, CC BY-SA 4.0",
      href: "https://commons.wikimedia.org/wiki/File:Emerald_Lake_in_Winter.jpg",
    },
  },
];

/** The hero pool for the season (summer when the season isn't known). */
export function landingPhotosFor(season: "summer" | "winter" | null): LandingPhoto[] {
  return season === "winter" ? WINTER_LANDING_PHOTOS : LANDING_PHOTOS;
}

/** Remembers the last hero photo so the next visit shows a different one. */
export const LANDING_PHOTO_COOKIE = "trekly_hero";

/**
 * A random photo from the pool, other than the one shown last time (when
 * there's another to choose from).
 */
export function pickLandingPhoto(
  photos: LandingPhoto[],
  lastSrc: string | undefined,
  random: () => number = Math.random,
): LandingPhoto {
  const others = photos.filter((photo) => photo.src !== lastSrc);
  const pool = others.length > 0 ? others : photos;
  return pool[Math.min(Math.floor(random() * pool.length), pool.length - 1)];
}
