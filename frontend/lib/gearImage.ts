import type { GearItem, ProductImage } from "./gearApi";

/**
 * Which picture a piece of gear gets. The mat, lists, setups and public
 * profiles show the licensed catalogue photo, or the line-art icon when
 * there's none (null). The owner's own photo is only ever shown to them,
 * in the item's detail view; the API and storage policies never hand it to
 * anyone else (migration 6e2f4b8d1a37).
 */
export function matImage(item: Pick<GearItem, "product">): ProductImage | null {
  return item.product?.image ?? null;
}

/** A thumbnail's picture: the owner's own photo (detail view only), then the catalogue photo. */
export function thumbImageUrl(productImage: ProductImage | null | undefined, ownPhotoUrl: string | null): string | null {
  return ownPhotoUrl ?? productImage?.url ?? null;
}
