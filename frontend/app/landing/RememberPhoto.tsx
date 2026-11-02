"use client";

import { useEffect } from "react";
import { LANDING_PHOTO_COOKIE } from "@/lib/landingPhotos";

/** Notes this visit's hero photo so the server skips it next time. */
export default function RememberPhoto({ src }: { src: string }) {
  useEffect(() => {
    document.cookie = `${LANDING_PHOTO_COOKIE}=${encodeURIComponent(src)}; path=/landing; max-age=31536000; samesite=lax`;
  }, [src]);
  return null;
}
