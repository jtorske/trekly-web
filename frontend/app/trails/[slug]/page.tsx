import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { cache } from "react";
import { absoluteUrl, SITE_NAME, trailHref } from "@/lib/site";
import { jsonLdScript, trailDescription, trailImage, trailJsonLd, trailTitle } from "@/lib/trailSeo";
import { getTrailBySlug, TrailApiUnavailable } from "@/lib/trailsServer";
import TrailPageClient from "../TrailPageClient";
import styles from "../page.module.css";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/** One lookup per request, shared by the metadata and the page. "unavailable" when the API is down. */
const loadTrail = cache(async (slug: string) => {
  try {
    return await getTrailBySlug(decodeURIComponent(slug));
  } catch (error) {
    if (error instanceof TrailApiUnavailable) return "unavailable" as const;
    throw error;
  }
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const trail = await loadTrail(slug);
  if (trail === "unavailable") return { title: "Trail", robots: { index: false } };
  if (!trail) return { title: "Trail not found", robots: { index: false } };

  const path = trailHref(trail);
  const title = trailTitle(trail);
  const description = trailDescription(trail);
  const image = trailImage(trail);
  const images = image ? [{ url: image.url, width: image.width, height: image.height, alt: image.alt }] : undefined;
  return {
    title,
    description,
    alternates: { canonical: path },
    // Retired trails still resolve for bookmarks, but leave search over time.
    ...(trail.retired_at ? { robots: { index: false, follow: true } } : {}),
    // A page's openGraph replaces the layout's whole object, so the site
    // name and locale have to be repeated here.
    openGraph: {
      type: "website",
      siteName: SITE_NAME,
      locale: "en_CA",
      url: path,
      title,
      description,
      ...(images ? { images } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      ...(images ? { images } : {}),
    },
  };
}

export default async function TrailPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const query = await searchParams;
  const trail = await loadTrail(slug);

  if (trail === "unavailable") {
    return (
      <main className={styles.page}>
        <div className={styles.wrap}>
          <Link href="/trail-list" className={styles.backLink}>
            ← Explore trails
          </Link>
          <div className={styles.status}>
            <h1 className={styles.notFoundTitle}>Trail unavailable</h1>
            <p>We couldn&apos;t load this trail right now. Try again in a moment.</p>
          </div>
        </div>
      </main>
    );
  }
  if (!trail) notFound();
  // /trails/Lake-Agnes-Tea-House and the like: one canonical URL.
  if (trail.slug !== decodeURIComponent(slug)) {
    const rest = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      for (const one of Array.isArray(value) ? value : value ? [value] : []) rest.append(key, one);
    }
    permanentRedirect(trailHref(trail, rest.toString()));
  }

  const save = typeof query.save === "string" ? query.save : null;
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLdScript(trailJsonLd(trail, absoluteUrl(trailHref(trail)))) }}
      />
      <TrailPageClient trail={trail} saveParam={save} />
    </>
  );
}
