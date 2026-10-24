"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./SiteFooter.module.css";

/** Footer copy shared by the landing hero and every other page. */
export function FooterNotice({ className }: { className?: string }) {
  return (
    <footer className={className}>
      <p>© 2026 Jordan Torske. All rights reserved.</p>
      <p>Trekly™ and the Trekly logo are trademarks of Jordan Torske.</p>
      <p>
        Trail data and permit information may change. Always check with
        Parks Canada before your trip.
      </p>
      <p>
        <Link href="/privacy">Privacy Policy</Link>
        <span aria-hidden="true"> • </span>
        <Link href="/terms">Terms of Use</Link>
      </p>
    </footer>
  );
}

/** Site-wide footer: transparent, sitting straight on the page background. */
export default function SiteFooter() {
  const pathname = usePathname();
  // The landing hero carries its own footer, overlaid on the photo.
  if (pathname === "/landing" || pathname === "/") return null;

  return <FooterNotice className={styles.footer} />;
}
