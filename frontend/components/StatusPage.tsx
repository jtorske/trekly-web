import Link from "next/link";
import type { ReactNode } from "react";
import ui from "./ui.module.css";
import styles from "./StatusPage.module.css";

/**
 * A whole-page message in Trekly's look: the 404, the error boundary and the
 * global error page. A ridge line with a trail that fades out, a heading,
 * a line of help, and actions led by Explore.
 */
export default function StatusPage({
  eyebrow,
  title,
  children,
  actions,
  headingLevel = 1,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  /** Extra buttons before the Explore link (e.g. "Try again"). */
  actions?: ReactNode;
  headingLevel?: 1 | 2;
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <svg className={styles.art} viewBox="0 0 240 120" aria-hidden="true">
          <path className={styles.ridgeBack} d="M0 96 L46 52 L70 70 L108 28 L150 74 L176 56 L240 96" />
          <path className={styles.ridge} d="M0 112 L38 82 L64 96 L104 58 L136 88 L170 68 L206 92 L240 80" />
          <path className={styles.trail} d="M18 118 C 60 112, 70 104, 98 104 S 140 98, 150 92" />
          <circle className={styles.marker} cx="156" cy="88" r="4" />
        </svg>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <Heading className={styles.title}>{title}</Heading>
        <div className={styles.body}>{children}</div>
        <div className={styles.actions}>
          {actions}
          <Link href="/trail-list" className={actions ? ui.secondary : ui.primary}>
            Explore trails
          </Link>
          <Link href="/" className={ui.ghost}>
            Back to Trekly
          </Link>
        </div>
      </div>
    </main>
  );
}
