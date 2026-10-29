import type { Metadata } from "next";
import Link from "next/link";
import styles from "@/components/LegalPage.module.css";

export const metadata: Metadata = {
  title: "Privacy Policy · Trekly",
  description: "What Trekly collects, how it's used, and the choices you have.",
};

const CONTACT_EMAIL = "treklyusersupport@gmail.com";

export default function PrivacyPage() {
  return (
    <main className={styles.page}>
      <article className={styles.sheet}>
        <h1 className={styles.title}>Privacy Policy</h1>
        <p className={styles.updated}>Last updated: October 28, 2026</p>
        <p className={styles.summary}>
          Trekly collects only what it needs to run your account, your trip plans, and your permit
          alerts. It does not sell your personal information or show you ads based on it.
        </p>

        <h2>Who we are</h2>
        <p>
          Trekly is a hiking and backpacking web app operated by Jordan Torske in Calgary, Alberta,
          Canada (&ldquo;Trekly,&rdquo; &ldquo;we,&rdquo; &ldquo;us&rdquo;). You can contact us about
          privacy at <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>

        <h2>Information we collect</h2>
        <h3>Information you give us</h3>
        <ul>
          <li>
            <strong>Account details:</strong> your email address and password when you sign up with
            email. Passwords are stored hashed by our authentication provider; we never see them in
            plain text.
          </li>
          <li>
            <strong>Google sign-in:</strong>{" "}if you choose &ldquo;Sign in with Google,&rdquo; Google
            shares your name, email address, and profile picture with us. We don&apos;t receive your
            Google password or access to your Google account.
          </li>
          <li>
            <strong>Profile:</strong> your display name, profile picture, and anything else you add
            to your profile.
          </li>
          <li>
            <strong>Photos:</strong> any photos you upload.
          </li>
          <li>
            <strong>Trip and gear data:</strong> trails you save, trip plans, gear lists, and
            loadouts you create.
          </li>
          <li>
            <strong>Permit alerts:</strong> the campsites, dates, and party details you ask us to
            watch, and the email address we send alerts to.
          </li>
          <li>
            <strong>Messages to us:</strong> anything you send when you contact us.
          </li>
        </ul>

        <h3>Information collected automatically</h3>
        <ul>
          <li>
            <strong>Technical data:</strong> IP address, browser type, and pages visited, collected
            in standard server logs by our hosting providers.
          </li>
          <li>
            <strong>Cookies and local storage:</strong> used to keep you signed in and remember your
            settings.
          </li>
        </ul>
        <p>
          We don&apos;t currently use analytics, advertising trackers, or your device&apos;s
          location. If that changes, we&apos;ll update this policy first.
        </p>
        <p>
          You can use much of Trekly without an account. We only collect account information when
          you choose to sign up.
        </p>

        <h2>How we use your information</h2>
        <ul>
          <li>To create and secure your account and sign you in.</li>
          <li>To save and show your trails, trip plans, and gear.</li>
          <li>
            To check reservation availability and email you when a campsite you&apos;re watching
            opens up.
          </li>
          <li>To send service messages, such as sign-up confirmation and password resets.</li>
          <li>To fix bugs, prevent abuse, and improve Trekly.</li>
          <li>To respond to you when you contact us.</li>
        </ul>
        <p>
          We don&apos;t send marketing emails or newsletters. We only email you about your account
          and the alerts you set up.
        </p>

        <h2>What other users can see</h2>
        <p>
          Trekly profiles are public by default, so other people can see your profile at its
          profile link. You choose what appears on it in Settings → Privacy:
        </p>
        <ul>
          <li>
            Shown even when your profile is private: your username, display name, and profile
            picture.
          </li>
          <li>Shown whenever your profile is public: your bio.</li>
          <li>
            Public by default, and you can hide each one: your Trail Journal and badges, rank, gear
            and loadouts, and saved trails.
          </li>
          <li>
            Private by default, and you can choose to show them: your trip plans. Public trip plans
            show where and when you&apos;ll be on a trail, so think carefully before sharing them.
          </li>
          <li>
            Always private: your email address, your permit alerts, and anything not listed above.
          </li>
        </ul>
        <p>
          You can make your whole profile private at any time, hide the dates of your hikes, and
          choose whether search engines can show your profile (off by default). Changes take effect
          right away. If you also turn on Show me in community features (off by default), the trail
          pages for trails you&apos;ve hiked can show your username, display name and profile
          picture, plus any notes and photos you&apos;ve added to those hikes, without dates if
          you&apos;ve chosen to hide them. Other users can report a trip note they believe breaks our Terms of Use. If
          you joined Trekly before public profiles were introduced, your profile
          stays private until you change your settings.
        </p>
        <p>
          Other signed-in users can report a profile they believe breaks our Terms of Use. A report
          includes the profile, the trip note if one was reported, the reason and any details
          given, and the reporter&apos;s account so we can follow up. It&apos;s sent only to us, and
          we never tell the reported person who reported them.
        </p>

        <h2>Service providers</h2>
        <p>
          We share information only with providers that help run Trekly, and only what they need:
        </p>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th scope="col">Provider</th>
                <th scope="col">What it does</th>
                <th scope="col">Data involved</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Supabase</td>
                <td>Accounts, sign-in, database, photo storage, and account emails</td>
                <td>Account, profile, photos, trip and gear data, email address</td>
              </tr>
              <tr>
                <td>Vercel</td>
                <td>Hosts the website</td>
                <td>Technical data, server logs</td>
              </tr>
              <tr>
                <td>Render</td>
                <td>Hosts the Trekly API</td>
                <td>Technical data, app data</td>
              </tr>
              <tr>
                <td>GitHub</td>
                <td>Runs the scheduled permit alert checks</td>
                <td>Alert details, email address for alerts</td>
              </tr>
              <tr>
                <td>Google</td>
                <td>&ldquo;Sign in with Google&rdquo; (only if you use it)</td>
                <td>Name, email, profile picture</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>
          Some of these providers store data outside Canada, including in the United States, where
          it may be accessible to authorities under local law. We may also disclose information if
          required by law, or to protect the safety of users or the public.
        </p>
        <p>
          Trekly is not affiliated with Parks Canada. When we check campsite availability for your
          alerts, we don&apos;t send Parks Canada your personal information.
        </p>

        <h2>How long we keep it</h2>
        <p>
          We keep your information while your account is active. If you delete your account, we
          delete your personal information, including your photos, within 30 days, except where we
          need to keep it longer for legal reasons. Our hosting providers keep server logs for a
          limited time under their own retention policies.
        </p>

        <h2>Your choices and rights</h2>
        <p>You can:</p>
        <ul>
          <li>View and edit your profile and saved data in the app.</li>
          <li>
            Choose what&apos;s public on your profile, or make it fully private, in Settings →
            Privacy.
          </li>
          <li>Stop any permit alert at any time.</li>
          <li>Ask for a copy of your personal information, or ask us to correct it.</li>
          <li>Delete your account at any time from within the app.</li>
          <li>
            Contact us at <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> with any other
            privacy request.
          </li>
        </ul>
        <p>
          We&apos;ll respond within 30 days. If you&apos;re not satisfied with our answer, you can
          contact the{" "}
          <a href="https://www.priv.gc.ca/" target="_blank" rel="noopener noreferrer">
            Office of the Privacy Commissioner of Canada
          </a>
          .
        </p>

        <h2>Security</h2>
        <p>
          We use encryption in transit (HTTPS), hashed passwords, and access controls on our
          database. No system is perfectly secure, so please use a strong, unique password.
        </p>

        <h2>Children</h2>
        <p>
          Trekly is not intended for children under 13. We don&apos;t knowingly collect information
          from them. If you believe a child has given us information, contact us and we&apos;ll
          delete it.
        </p>

        <h2>Changes to this policy</h2>
        <p>
          If we make significant changes, we&apos;ll update the date above and notify you by email
          or in the app before they take effect.
        </p>

        <h2>Contact</h2>
        <p>
          Jordan Torske, Trekly &mdash; <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}
          &mdash; Calgary, Alberta, Canada
        </p>

        <p className={styles.related}>
          See also our <Link href="/terms">Terms of Use</Link>.
        </p>
      </article>
    </main>
  );
}
