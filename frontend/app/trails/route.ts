import { NextResponse, type NextRequest } from "next/server";
import { getTrailById, TrailApiUnavailable } from "@/lib/trailsServer";

/**
 * The old trail URL, /trails?id={uuid}: a permanent (301) redirect to the
 * trail's page, /trails/{slug}, keeping the rest of the query (a stay
 * ?start=…&nights=… from an alert email, or ?save= after sign-in).
 * Bare /trails goes to Explore.
 */
export async function GET(request: NextRequest) {
  const url = request.nextUrl;
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.redirect(new URL("/trail-list", url), 301);

  let trail;
  try {
    trail = await getTrailById(id);
  } catch (error) {
    if (!(error instanceof TrailApiUnavailable)) throw error;
    // Not permanent: try again once the API is back.
    return new NextResponse("Trekly couldn't load this trail right now. Try again in a moment.", {
      status: 503,
      headers: { "Retry-After": "60", "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  if (!trail) {
    return NextResponse.redirect(new URL("/trail-list", url), 302);
  }

  const target = new URL(`/trails/${encodeURIComponent(trail.slug)}`, url);
  for (const [key, value] of url.searchParams) {
    if (key !== "id") target.searchParams.append(key, value);
  }
  return NextResponse.redirect(target, 301);
}
