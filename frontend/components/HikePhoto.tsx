"use client";

import { useEffect, useState } from "react";
import ui from "@/components/ui.module.css";
import { signedImageUrl } from "@/lib/storage";

/**
 * Someone's journal photo from the private hike-photos bucket. Visitors can
 * sign it only while that person's Trail Journal is public (storage RLS),
 * so a hidden journal's photo never loads, whatever the page asks for.
 */
export default function HikePhoto({ path, alt, className }: { path: string; alt: string; className: string }) {
  const [url, setUrl] = useState<{ path: string; url: string | null } | null>(null);
  useEffect(() => {
    let live = true;
    signedImageUrl("hike-photos", path).then((signed) => live && setUrl({ path, url: signed }));
    return () => {
      live = false;
    };
  }, [path]);
  const current = url?.path === path ? url.url : null;
  if (!current) return <span className={`${className} ${ui.skeleton}`} aria-hidden="true" />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={current} alt={alt} className={className} loading="lazy" />;
}
