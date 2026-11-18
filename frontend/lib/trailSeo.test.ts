import test from "node:test";
import assert from "node:assert/strict";
import { jsonLdScript, trailDescription, trailImage, trailJsonLd, trailTitle } from "./trailSeo.ts";
import type { TrailDetail } from "./trailsApi";

const AGNES: TrailDetail = {
  id: "t1", slug: "lake-agnes-tea-house", name: "Lake Agnes Tea House", region: "Banff National Park, AB",
  terrain: "easy", country_code: "CA", province_code: "AB", park_name: "Banff National Park", park_type: "national",
  typical_duration_nights: 0, route_type: "out_and_back", distance_km: 7.2, elevation_gain_m: 400,
  popularity_rank: 1, latitude: 51.4167, longitude: -116.2167, retired_at: null, photo: null, route_map: null,
  max_elevation_m: 2135, climate_zone: "alpine",
  description: "A steady climb from Lake Louise to a historic tea house. Bring cash for tea.",
  seasonal_conditions: [], has_watchable_campgrounds: false, trail_permit: false, booked_through: null,
};

test("titles name the trail and its park", () => {
  assert.equal(trailTitle(AGNES), "Lake Agnes Tea House Hike – Banff National Park");
  assert.equal(
    trailTitle({ ...AGNES, park_name: null, region: "Kananaskis Country, AB" }),
    "Lake Agnes Tea House Hike – Kananaskis Country",
  );
});

test("descriptions come from the trail's own data", () => {
  assert.equal(
    trailDescription(AGNES),
    "An easy 7.2 km out-and-back day hike in Banff National Park, Alberta, with 400 m of elevation gain. "
      + "A steady climb from Lake Louise to a historic tea house.",
  );
  const overnight = trailDescription({ ...AGNES, terrain: "difficult", typical_duration_nights: 3, description: null });
  assert.match(overnight, /^A difficult 7\.2 km out-and-back 3-night backpacking trip in Banff National Park, Alberta/);
  // A first sentence that doesn't fit whole is left out, never cut off.
  const long = trailDescription({ ...AGNES, description: `${"word ".repeat(30)}end. More.` });
  assert.ok(long.length <= 160);
  assert.ok(!long.includes("word") && !long.includes("…"));
});

test("the social image is the photo, else the route map", () => {
  assert.equal(trailImage(AGNES), null);
  const map = { hero_url: "https://cdn/map.webp", thumb_url: "", width: 1600, height: 900 };
  assert.equal(trailImage({ ...AGNES, route_map: map })?.url, "https://cdn/map.webp");
});

test("structured data is a tourist attraction with coordinates and region", () => {
  const data = trailJsonLd(AGNES, "https://trekly.example/trails/lake-agnes-tea-house");
  assert.deepEqual(data["@type"], ["TouristAttraction", "Place"]);
  assert.deepEqual(data.geo, { "@type": "GeoCoordinates", latitude: 51.4167, longitude: -116.2167 });
  assert.deepEqual(data.address, { "@type": "PostalAddress", addressRegion: "Alberta", addressCountry: "CA" });
  assert.deepEqual(data.containedInPlace, { "@type": "Park", name: "Banff National Park" });
  assert.equal(jsonLdScript({ name: "</script><b>" }), '{"name":"\\u003c/script>\\u003cb>"}');
});
