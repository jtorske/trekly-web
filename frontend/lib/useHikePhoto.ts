"use client";

import { useEffect, useState } from "react";
import { signedImageUrl } from "./storage";

/** A signed URL for a private journal photo, or null while it loads. */
export function useHikePhoto(path: string | null) {
  const [url, setUrl] = useState<{ path: string; url: string | null } | null>(null);
  useEffect(() => {
    if (!path) return;
    let live = true;
    signedImageUrl("hike-photos", path).then((signed) => live && setUrl({ path, url: signed }));
    return () => {
      live = false;
    };
  }, [path]);
  return path && url?.path === path ? url.url : null;
}
