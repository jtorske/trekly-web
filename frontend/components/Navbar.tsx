"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import styles from "./Navbar.module.css";

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false);

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
        <Link href="/signup" className={`${styles.link} ${styles.signup}`}>
          Sign up
        </Link>

        <Link href="/login" className={`${styles.link} ${styles.login}`}>
          Login
        </Link>
      </div>
    </nav>
  );
}
