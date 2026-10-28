import test from "node:test";
import assert from "node:assert/strict";
import { matImage, thumbImageUrl } from "./gearImage.ts";
import type { GearItem, ProductImage, ProductSummary } from "./gearApi.ts";

const photo: ProductImage = {
  url: "https://images.example.com/stove.webp",
  alt_text: "Stove",
  license: "Brand press kit",
  attribution: "Example Brand",
  source_url: "https://example.com/press",
};

function item(image: ProductImage | null, withProduct = true): Pick<GearItem, "product" | "image_path"> {
  return {
    product: withProduct ? ({ image } as ProductSummary) : null,
    image_path: "owner/0b6a2c1e-0000-4000-8000-000000000000.webp",
  };
}

test("the mat shows the catalogue photo, never the owner's upload", () => {
  assert.equal(matImage(item(photo)), photo);
});

test("the mat falls back to the line-art icon without a catalogue photo", () => {
  assert.equal(matImage(item(null)), null);
  assert.equal(matImage(item(null, false)), null);
});

test("the detail view prefers the owner's own photo, then the catalogue photo", () => {
  assert.equal(thumbImageUrl(photo, "https://signed.example/own"), "https://signed.example/own");
  assert.equal(thumbImageUrl(photo, null), photo.url);
  assert.equal(thumbImageUrl(null, null), null);
});
