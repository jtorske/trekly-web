import Link from "next/link";
import styles from "./not-found.module.css";

// Replaces Next's default 404, whose dark-mode styles put white text on the
// site's cream background.
export default function NotFound() {
  return (
    <main className={styles.page}>
      <div>
        <p className={styles.code}>404</p>
        <h1 className={styles.title}>This trail doesn&apos;t go anywhere</h1>
        <p className={styles.body}>
          The page you&apos;re looking for doesn&apos;t exist or has moved.
        </p>
        <div className={styles.links}>
          <Link href="/landing" className={styles.link}>
            Back to Trekly
          </Link>
          <Link href="/trail-list" className={styles.link}>
            Explore trails
          </Link>
        </div>
      </div>
    </main>
  );
}
