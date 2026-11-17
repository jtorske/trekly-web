import type { Metadata } from "next";
import Link from "next/link";
import styles from "@/components/LegalPage.module.css";

export const metadata: Metadata = {
  title: "Community Guidelines · Trekly",
  description: "How to share hikes, photos and notes on Trekly: be respectful, post your own photos, no spam, and keep other people's plans private.",
};

const CONTACT_EMAIL = "treklyusersupport@gmail.com";

export default function GuidelinesPage() {
  return (
    <main className={styles.page}>
      <article className={styles.sheet}>
        <h1 className={styles.title}>Community Guidelines</h1>
        <p className={styles.updated}>Last updated: November 19, 2026</p>
        <p className={styles.summary}>
          Trekly is a place to share time outdoors: the hikes you&apos;ve done, what you saw, and
          what you learned. These guidelines apply to everything you post, including hike notes,
          photos, Activity posts, comments, your bio and your profile photo. They sit alongside
          our <Link href="/terms">Terms of Use</Link>.
        </p>

        <h2>Be respectful</h2>
        <ul>
          <li>Treat other hikers the way you would on the trail. Disagree kindly, or move on.</li>
          <li>
            No harassment, bullying, threats, or hate based on who someone is (for example race,
            ethnicity, religion, disability, gender, sexual orientation or age).
          </li>
          <li>
            Don&apos;t use follows, high fives, comments or reports to pester someone or to keep
            contacting a person who doesn&apos;t want it.
          </li>
          <li>Keep it suitable for a general audience: no sexual content and no graphic violence.</li>
          <li>Don&apos;t pretend to be another person, group or organization.</li>
        </ul>

        <h2>Only post your own photos</h2>
        <ul>
          <li>
            Post photos you took yourself, or that you have permission to share. Don&apos;t post
            other people&apos;s photos, stock images, or screenshots of someone else&apos;s work.
          </li>
          <li>
            Be thoughtful about people in your photos. Don&apos;t post photos that identify
            someone who didn&apos;t agree to be shared, and never post intimate or embarrassing
            images of anyone.
          </li>
        </ul>

        <h2>No spam or promotion</h2>
        <ul>
          <li>
            No advertising, affiliate links, selling, fundraising, or promoting a business,
            guiding service or social account.
          </li>
          <li>
            Don&apos;t post the same thing again and again, log hikes you didn&apos;t do, or
            create accounts to boost your own posts.
          </li>
          <li>Recommending gear you actually use is fine; being paid to post about it isn&apos;t.</li>
        </ul>

        <h2>Keep other people&apos;s locations and plans private</h2>
        <ul>
          <li>
            Don&apos;t share where someone else is, will be, or lives, including their campsite,
            trip dates, trailhead, vehicle or home, unless they&apos;ve shared it themselves.
          </li>
          <li>
            Don&apos;t repost someone&apos;s trip plans, routes or photos to show when they&apos;ll
            be away from home or alone in the backcountry.
          </li>
          <li>
            Be careful with sensitive places too: don&apos;t post the location of nesting sites,
            dens, rare plants, or closed or culturally sensitive areas.
          </li>
        </ul>

        <h2>No illegal or dangerous content</h2>
        <ul>
          <li>
            Nothing illegal, including content that sexualizes minors (which we report to
            Cybertip.ca and the police), and nothing that encourages someone to hurt themselves or
            others.
          </li>
          <li>
            Don&apos;t encourage breaking park rules, such as camping where it&apos;s not allowed,
            ignoring closures, feeding wildlife, or reselling permits.
          </li>
        </ul>

        <h2>How we keep Trekly safe</h2>
        <p>
          Text and photos you post are checked by an automated moderation service when you post
          or edit them. If something might break these guidelines, it&apos;s held for a person to
          review: you&apos;ll still see it, marked &ldquo;being reviewed,&rdquo; but nobody else
          will until it&apos;s approved. Automated checks make mistakes, so nothing is removed by
          the check alone.
        </p>
        <p>
          If you see something that breaks these guidelines, use <strong>Report</strong>{" "}on the
          post, note or profile. Reports are private; the person you report isn&apos;t told who
          sent it. When several people report the same thing, it&apos;s hidden until we review it.
        </p>
        <p>
          Depending on what happened, we may approve the content, hide it, send a warning,
          suspend the account for a while, or close it. We email you when we hide something you
          posted and tell you why. Serious or repeated problems, and anything involving harm to
          children, can lead straight to a ban.
        </p>
        <p>
          New accounts can&apos;t post photos or comments until their email address is confirmed,
          and can post a little less often during their first day.
        </p>

        <h2>Think we got it wrong?</h2>
        <p>
          Email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}within 30 days with your
          username and what you&apos;d like us to look at again. A person will review it.
        </p>
      </article>
    </main>
  );
}
