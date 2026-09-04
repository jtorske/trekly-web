"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import styles from "./Navbar.module.css";

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  useEffect(() => {
    const updateNavbar = () => {
      const hero = document.querySelector("main");
      setIsScrolled(
        hero
          ? hero.getBoundingClientRect().bottom <= 0
          : window.scrollY > window.innerHeight,
      );
    };

    updateNavbar();
    window.addEventListener("scroll", updateNavbar, { passive: true });

    return () => window.removeEventListener("scroll", updateNavbar);
  }, []);

  return (
    <nav className={`${styles.navbar} ${isScrolled ? styles.scrolled : ""}`}>
      <Link href="/landing" aria-label="Trekly home">
        <Image
          src="/TreklyLogoW.svg"
          alt="Trekly"
          width={82}
          height={81}
          className={styles.logo}
        />
      </Link>

      <div className={styles.links}>
        <Link href="/trail-list" className={styles.link}>
          Explore
        </Link>

        <Link href="/featured" className={styles.link}>
          Featured
        </Link>

        <Link href="/packplanner" className={styles.link}>
          Pack
        </Link>

        <Link href="/signup" className={`${styles.link} ${styles.signup}`}>
          Sign up
        </Link>

        <Link href="/login" className={`${styles.link} ${styles.login}`}>
          Login
        </Link>
      </div>

      <button
        type="button"
        className={styles.menuToggle}
        aria-label={
          isMenuOpen ? "Close navigation menu" : "Open navigation menu"
        }
        aria-expanded={isMenuOpen}
        aria-controls="mobile-navigation"
        onClick={() => setIsMenuOpen((open) => !open)}
      >
        <span />
        <span />
        <span />
      </button>

      {isMenuOpen && (
        <div id="mobile-navigation" className={styles.mobileMenu}>
          <Link
            href="/trail-list"
            className={styles.mobileMenuLink}
            onClick={() => setIsMenuOpen(false)}
          >
            Explore
          </Link>
          <Link
            href="/featured"
            className={styles.mobileMenuLink}
            onClick={() => setIsMenuOpen(false)}
          >
            Featured
          </Link>
          <Link
            href="/packplanner"
            className={styles.mobileMenuLink}
            onClick={() => setIsMenuOpen(false)}
          >
            Pack
          </Link>
          <Link
            href="/signup"
            className={`${styles.mobileMenuLink} ${styles.mobileMenuSignup}`}
            onClick={() => setIsMenuOpen(false)}
          >
            Sign up
          </Link>
          <Link
            href="/login"
            className={styles.mobileMenuLink}
            onClick={() => setIsMenuOpen(false)}
          >
            Login
          </Link>
        </div>
      )}
    </nav>
  );
}
