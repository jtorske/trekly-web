import type { Metadata } from "next";
import Link from "next/link";
import styles from "@/components/LegalPage.module.css";

export const metadata: Metadata = {
  title: "Terms of Use · Trekly",
  description: "The rules for using Trekly, including outdoor safety and permit alerts.",
};

const CONTACT_EMAIL = "treklyusersupport@gmail.com";

export default function TermsPage() {
  return (
    <main className={styles.page}>
      <article className={styles.sheet}>
        <h1 className={styles.title}>Terms of Use</h1>
        <p className={styles.updated}>Last updated: October 26, 2026</p>
        <p className={styles.summary}>
          By using Trekly, you agree to these terms. Trekly helps you plan hikes and backpacking
          trips, but you are responsible for your own safety in the backcountry.
        </p>

        <h2>Who can use Trekly</h2>
        <p>
          You must be at least 13 years old to use Trekly, and you need a parent or guardian&apos;s
          permission if you&apos;re under the age of majority where you live. These terms are an
          agreement between you and Jordan Torske, who operates Trekly (&ldquo;we,&rdquo;
          &ldquo;us&rdquo;).
        </p>

        <h2>Your account</h2>
        <ul>
          <li>Give accurate information when you sign up, and keep your password secure.</li>
          <li>
            You&apos;re responsible for activity on your account. Tell us at{" "}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> if you think someone else has
            accessed it.
          </li>
          <li>One person per account; don&apos;t share or sell accounts.</li>
        </ul>

        <h2>Outdoor safety</h2>
        <p>
          Hiking and backpacking carry real risks, including injury and death. Trail details,
          conditions, distances, difficulty ratings, and maps in Trekly may be incomplete, out of
          date, or wrong.
        </p>
        <ul>
          <li>
            Always check current conditions, closures, and warnings with Parks Canada or the land
            manager before you go.
          </li>
          <li>Carry proper navigation, gear, and supplies, and tell someone your plans.</li>
          <li>Use your own judgment. Don&apos;t rely on Trekly as your only source of information.</li>
        </ul>
        <p>
          <strong>You use trails and plan trips at your own risk.</strong>
        </p>

        <h2>Permit and campsite alerts</h2>
        <p>
          Trekly is not affiliated with, endorsed by, or connected to Parks Canada. Our alerts check
          publicly available reservation information and email you when something may have opened
          up.
        </p>
        <ul>
          <li>
            Alerts are best-effort. They may be delayed, missed, or wrong, and a site may be booked
            by someone else before you see the alert.
          </li>
          <li>
            Trekly does not make reservations for you. You must book directly through Parks Canada
            and follow its rules.
          </li>
          <li>
            We may limit how many alerts you can run, or pause alerts if the reservation system
            changes.
          </li>
        </ul>

        <h2>Acceptable use</h2>
        <p>Don&apos;t:</p>
        <ul>
          <li>Break the law or Parks Canada rules using Trekly.</li>
          <li>
            Post content that&apos;s illegal, harassing, hateful, or that infringes someone
            else&apos;s rights.
          </li>
          <li>Scrape, overload, or try to break into Trekly or its systems.</li>
          <li>Use Trekly to resell permits or reservations.</li>
          <li>Pretend to be someone else.</li>
        </ul>

        <h2>Your content</h2>
        <p>
          You own what you create in Trekly, such as trip plans, gear lists, and photos. You give us
          permission to store, display, and process it only so we can run Trekly for you. Only
          upload photos you took or have the right to share. We may remove content that breaks these terms.
        </p>

        <h2>Our content</h2>
        <p>
          The Trekly name, logo, app design, and code belong to Jordan Torske. Don&apos;t copy or
          reuse them without permission. Trail information comes from public sources, including
          Parks Canada, provincial park agencies, and OpenStreetMap contributors. Campsite
          reservation information comes from Parks Canada. These sources keep their own rights and
          terms, and trail photos are credited to their photographers under their own licenses.
        </p>

        <h2>Changes and ending your use</h2>
        <p>
          We may change or discontinue features, or Trekly itself, at any time. If we add paid
          features, we&apos;ll show you the price and any extra terms before you pay. You can stop
          using Trekly and delete your account whenever you like. We may suspend or close accounts
          that break these terms.
        </p>

        <h2>Disclaimers</h2>
        <p>
          Trekly is provided &ldquo;as is&rdquo; and &ldquo;as available,&rdquo; without warranties
          of any kind, including accuracy, availability, or fitness for a particular purpose, to the
          extent the law allows.
        </p>

        <h2>Limitation of liability</h2>
        <p>
          To the fullest extent permitted by law, we&apos;re not liable for indirect or
          consequential losses, or for injury, loss, or damage arising from your outdoor activities
          or from relying on information or alerts in Trekly. Nothing in these terms limits rights
          you have under consumer protection law that can&apos;t be waived.
        </p>

        <h2>Governing law</h2>
        <p>
          These terms are governed by the laws of Alberta and the federal laws of Canada that apply
          there. Disputes will be handled in the courts of Alberta, unless your local consumer law
          gives you the right to use your own courts.
        </p>

        <h2>Changes to these terms</h2>
        <p>
          If we make significant changes, we&apos;ll update the date above and notify you by email
          or in the app. Continuing to use Trekly after that means you accept the new terms.
        </p>

        <h2>Contact</h2>
        <p>
          Jordan Torske, Trekly &mdash; <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}
          &mdash; Calgary, Alberta, Canada
        </p>

        <p className={styles.related}>
          See also our <Link href="/privacy">Privacy Policy</Link>.
        </p>
      </article>
    </main>
  );
}
