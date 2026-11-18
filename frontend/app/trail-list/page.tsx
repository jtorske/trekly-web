import type { Metadata } from "next";
import { exploreRequest, exploreRequestKey, parseExploreParams } from "@/lib/exploreFilters";
import { searchExploreOnServer } from "@/lib/trailsServer";
import ExploreClient, { type ExploreInitial } from "./ExploreClient";

export const metadata: Metadata = {
  title: "Explore Canadian hiking trails",
  description:
    "Browse Canada's best hikes on a map: day hikes and backpacking routes in national and provincial parks, with distance, elevation and campsites.",
  // Filtered views (?q=, ?province=…) all point at the one Explore page.
  alternates: { canonical: "/trail-list" },
};

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

/**
 * Explore. The first page of results for this URL is fetched here, so the
 * trail list is in the HTML (for search engines and a faster first paint);
 * the browser takes over from there: the map, "near me", typing.
 */
export default async function ExplorePage({ searchParams }: Props) {
  const query = await searchParams;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    for (const one of Array.isArray(value) ? value : value ? [value] : []) params.append(key, one);
  }
  const filters = parseExploreParams(params);
  let initial: ExploreInitial | null = null;
  // "Near me" needs the browser's position; that search can't run here.
  if (!filters.near) {
    const request = exploreRequest(filters);
    const found = await searchExploreOnServer(request);
    if (found) initial = { key: exploreRequestKey(request), trails: found.trails, total: found.total, facets: found.facets };
  }
  return <ExploreClient initial={initial} />;
}
