import test from "node:test";
import assert from "node:assert/strict";
import { creditPlace, photoCredit } from "./trailPhoto.ts";
import type { TrailPhoto } from "./trailsApi";

const PHOTO: TrailPhoto = {
  hero_url: "https://x.supabase.co/storage/v1/object/public/trail-photos/a/b-hero.webp",
  thumb_url: "https://x.supabase.co/storage/v1/object/public/trail-photos/a/b-thumb.webp",
  width: 1600,
  height: 900,
  photographer: "Wilson Hui",
  license: "CC BY-SA 4.0",
  license_url: "https://creativecommons.org/licenses/by-sa/4.0/",
  source_url: "https://www.flickr.com/photos/51942038@N04/15464773570",
  origin: "Flickr",
};

test("credits the photographer and license, linking to the source", () => {
  assert.deepEqual(photoCredit(PHOTO), {
    text: "Photo: Wilson Hui, CC BY-SA 4.0",
    href: "https://www.flickr.com/photos/51942038@N04/15464773570",
    title: "View the original on Flickr",
  });
});

test("the owner's own photo is credited by name only, with no link", () => {
  const own = { ...PHOTO, photographer: " Jordan Torske ", license: null, license_url: null, source_url: null, origin: null };
  assert.deepEqual(photoCredit(own), { text: "Photo: Jordan Torske", href: null, title: null });
});

test("never links to a non-web URL", () => {
  assert.equal(photoCredit({ ...PHOTO, source_url: "javascript:alert(1)" }).href, null);
  assert.equal(photoCredit({ ...PHOTO, source_url: "not a url" }).href, null);
});

test("a park photo names the park before the photographer", () => {
  assert.equal(
    photoCredit({ ...PHOTO, scope: "park" }, "Jasper National Park").text,
    "Photo: Jasper National Park · Wilson Hui, CC BY-SA 4.0",
  );
  // Trail and nearby photos, and a park photo with no place to name, stay as they were.
  assert.equal(photoCredit({ ...PHOTO, scope: "trail" }, "Jasper National Park").text, "Photo: Wilson Hui, CC BY-SA 4.0");
  assert.equal(photoCredit({ ...PHOTO, scope: "nearby" }, "Jasper National Park").text, "Photo: Wilson Hui, CC BY-SA 4.0");
  assert.equal(photoCredit({ ...PHOTO, scope: "park" }, "  ").text, "Photo: Wilson Hui, CC BY-SA 4.0");
});

test("the credit's place is the park, else the region", () => {
  assert.equal(creditPlace({ park_name: "Fundy National Park", region: "Fundy National Park, NB" }), "Fundy National Park");
  assert.equal(creditPlace({ park_name: null, region: "Kananaskis, AB" }), "Kananaskis, AB");
  assert.equal(creditPlace({}), null);
});
