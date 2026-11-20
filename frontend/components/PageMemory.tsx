"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { LAST_PAGE_KEY, returnablePath } from "@/lib/returnTo";

/**
 * Remembers the last page outside Settings (per tab, in sessionStorage), so
 * Settings' "← Back to profile" link can return there. Renders nothing.
 */
export default function PageMemory() {
  const pathname = usePathname();
  useEffect(() => {
    const here = `${window.location.pathname}${window.location.search}`;
    const path = returnablePath(here, window.location.origin);
    if (!path) return;
    try {
      sessionStorage.setItem(LAST_PAGE_KEY, path);
    } catch {
      // Storage blocked: the link falls back to the referrer or /profile.
    }
  }, [pathname]);
  return null;
}
