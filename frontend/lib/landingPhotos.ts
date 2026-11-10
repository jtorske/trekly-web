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
  { src: "/images/IMG_9832.jpeg" },
  { src: "/images/IMG_9878.jpeg" },
];

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
