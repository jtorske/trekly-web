"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "./AuthProvider";
import Avatar from "./Avatar";
import { nextQuery } from "@/lib/authLogic";
import { useProfile } from "@/lib/useProfile";
import styles from "./Navbar.module.css";

const LINKS = [
  { href: "/trail-list", label: "Explore" },
  { href: "/gear", label: "Gear" },
  { href: "/campalert", label: "CampAlert" },
];

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { status, user } = useAuth();
  const { profile } = useProfile();
  const pathname = usePathname();
  const isAuthPage = /^\/(login|signup|forgot-password|reset-password|auth)/.test(pathname);
  const returnTo = isAuthPage ? "" : nextQuery(pathname);

  useEffect(() => {
    const updateNavbar = () => {
      const hero = document.querySelector("main");
      setIsScrolled(
        hero ? hero.getBoundingClientRect().bottom <= 0 : window.scrollY > window.innerHeight,
      );
    };

    updateNavbar();
    window.addEventListener("scroll", updateNavbar, { passive: true });

    return () => window.removeEventListener("scroll", updateNavbar);
  }, []);

  const displayName = profile?.display_name ?? null;
  const email = user?.email ?? null;
  const accountLabel = `Your profile${displayName ? ` (${displayName})` : ""}`;

  const account =
    status === "signedIn" ? (
      <Link href="/profile" className={styles.avatarLink} aria-label={accountLabel} title="Your profile">
        <Avatar path={profile?.avatar_path} name={displayName} email={email} size={34} />
      </Link>
    ) : status === "loading" ? (
      // Reserve the space while the session restores so buttons don't flash.
      <span className={styles.avatarPlaceholder} aria-hidden="true" />
    ) : (
      <>
        <Link href={`/signup${returnTo}`} className={`${styles.link} ${styles.signup}`}>
          Sign up
        </Link>
        <Link href={`/login${returnTo}`} className={`${styles.link} ${styles.login}`}>
          Sign in
        </Link>
      </>
    );

  return (
    <nav className={`${styles.navbar} ${isScrolled ? styles.scrolled : ""}`}>
      <Link href="/landing" aria-label="Trekly home">
        <Image src="/TreklyLogoW.svg" alt="Trekly" width={82} height={81} className={styles.logo} />
      </Link>

      <div className={styles.links}>
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={styles.link}
            aria-current={pathname.startsWith(link.href) ? "page" : undefined}
          >
            {link.label}
          </Link>
        ))}
        {account}
      </div>

      <div className={styles.mobileBar}>
        {status === "signedIn" && account}
        <button
          type="button"
          className={styles.menuToggle}
          aria-label={isMenuOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={isMenuOpen}
          aria-controls="mobile-navigation"
          onClick={() => setIsMenuOpen((open) => !open)}
        >
          <span />
          <span />
          <span />
        </button>
      </div>

      {isMenuOpen && (
        <div id="mobile-navigation" className={styles.mobileMenu}>
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} className={styles.mobileMenuLink} onClick={() => setIsMenuOpen(false)}>
              {link.label}
            </Link>
          ))}
          {status === "signedIn" ? (
            <Link href="/profile" className={styles.mobileMenuLink} onClick={() => setIsMenuOpen(false)}>
              Your profile
            </Link>
          ) : (
            <>
              <Link
                href={`/signup${returnTo}`}
                className={`${styles.mobileMenuLink} ${styles.mobileMenuSignup}`}
                onClick={() => setIsMenuOpen(false)}
              >
                Sign up
              </Link>
              <Link href={`/login${returnTo}`} className={styles.mobileMenuLink} onClick={() => setIsMenuOpen(false)}>
                Sign in
              </Link>
            </>
          )}
        </div>
      )}
    </nav>
  );
}
