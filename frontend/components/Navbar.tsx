"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthProvider";
import AccountMenu from "./AccountMenu";
import Avatar from "./Avatar";
import MobileMenu from "./MobileMenu";
import { NAV_LINKS, isNavCurrent } from "@/lib/accountMenu";
import { nextQuery } from "@/lib/authLogic";
import { useProfile } from "@/lib/useProfile";
import styles from "./Navbar.module.css";

/** Matches the stylesheet: below this the header shows one menu trigger. */
const DESKTOP_QUERY = "(min-width: 900px)";

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isPastHero, setIsPastHero] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  // Query string when the mobile menu opened, for highlighting profile tabs.
  const [menuSearch, setMenuSearch] = useState("");
  const menuTriggerRef = useRef<HTMLButtonElement>(null);
  const { status, user } = useAuth();
  const { profile } = useProfile();
  const pathname = usePathname();
  const isAuthPage = /^\/(login|signup|forgot-password|reset-password|auth)/.test(pathname);
  // Only the landing hero (a dark photo) keeps the see-through cream bar;
  // everywhere else the header is paper, blending into the topo background.
  const hasHero = pathname === "/landing" || pathname === "/";
  const overHero = hasHero && !isPastHero;
  const returnTo = isAuthPage ? "" : nextQuery(pathname);

  useEffect(() => {
    const updateNavbar = () => {
      const hero = document.querySelector("main");
      setIsScrolled(window.scrollY > 0);
      setIsPastHero(
        hero ? hero.getBoundingClientRect().bottom <= 0 : window.scrollY > window.innerHeight,
      );
    };

    updateNavbar();
    window.addEventListener("scroll", updateNavbar, { passive: true });

    return () => window.removeEventListener("scroll", updateNavbar);
  }, [pathname]);

  // Close the mobile menu on navigation (e.g. browser back) and if the
  // window widens to the desktop header.
  useEffect(() => {
    queueMicrotask(() => setIsMenuOpen(false));
  }, [pathname]);
  useEffect(() => {
    const desktop = window.matchMedia(DESKTOP_QUERY);
    const onChange = () => desktop.matches && setIsMenuOpen(false);
    desktop.addEventListener("change", onChange);
    return () => desktop.removeEventListener("change", onChange);
  }, []);

  const openMenu = () => {
    setMenuSearch(window.location.search);
    setIsMenuOpen(true);
  };
  const closeMenu = useCallback(() => setIsMenuOpen(false), []);

  const displayName = profile?.display_name ?? null;
  const email = user?.email ?? null;
  const identity = { displayName, email, avatarPath: profile?.avatar_path, isAdmin: profile?.is_admin === true };

  const account =
    status === "signedIn" ? (
      <AccountMenu identity={identity} triggerClassName={styles.avatarLink} />
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
    <nav
      className={`${styles.navbar} ${
        overHero ? styles.hero : isScrolled ? styles.scrolled : ""
      }`}
    >
      <Link href="/landing" aria-label="Trekly home" className={styles.logoLink}>
        {/* The logo SVG as a mask, filled with the current text colour: ink on
            paper, cream over the hero photo. */}
        <span className={styles.logo} />
      </Link>

      <div className={styles.links}>
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={styles.link}
            aria-current={isNavCurrent(pathname, link) ? "page" : undefined}
          >
            {link.label}
          </Link>
        ))}
        {account}
      </div>

      {/* Below 900px: one trigger. Signed in it's the avatar; signed out, ☰. */}
      <div className={styles.mobileBar}>
        {status === "signedIn" ? (
          <button
            ref={menuTriggerRef}
            type="button"
            className={`${styles.menuAvatar} ${styles.avatarLink}`}
            aria-label={`Open menu${displayName ? ` for ${displayName}` : ""}`}
            aria-haspopup="dialog"
            aria-expanded={isMenuOpen}
            aria-controls={isMenuOpen ? "mobile-navigation" : undefined}
            onClick={openMenu}
          >
            <Avatar path={identity.avatarPath} name={displayName} email={email} size={34} />
          </button>
        ) : status === "loading" ? (
          <span className={styles.avatarPlaceholder} aria-hidden="true" />
        ) : (
          <button
            ref={menuTriggerRef}
            type="button"
            className={styles.menuToggle}
            aria-label="Open menu"
            aria-haspopup="dialog"
            aria-expanded={isMenuOpen}
            aria-controls={isMenuOpen ? "mobile-navigation" : undefined}
            onClick={openMenu}
          >
            <span />
            <span />
            <span />
          </button>
        )}
      </div>

      {isMenuOpen && status !== "loading" && (
        <MobileMenu
          identity={status === "signedIn" ? identity : null}
          pathname={pathname}
          search={menuSearch}
          returnTo={returnTo}
          returnFocusTo={menuTriggerRef}
          onClose={closeMenu}
        />
      )}
    </nav>
  );
}
