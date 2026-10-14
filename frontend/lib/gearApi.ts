import { apiFetch } from "./api";

export type WeightUnit = "g" | "kg" | "oz" | "lb";
export type VolumeUnit = "ml" | "l" | "fl_oz" | "cu_in";
export type Condition = "new" | "good" | "worn" | "needs_repair" | "retired";

export interface SpecRow {
  key: string;
  label: string;
  value: number | string | boolean;
  unit: string | null;
}

export interface Subcategory {
  slug: string;
  name: string;
  icon_key: string;
}

export interface GearCategory extends Subcategory {
  description: string | null;
  subcategories: Subcategory[];
}

export interface CategoryRef {
  slug: string;
  name: string;
  icon_key: string;
  top_slug: string;
  top_name: string;
}

export interface BrandRef {
  id: string;
  slug: string;
  name: string;
}

export interface Brand extends BrandRef {
  product_count: number;
}

export interface ProductImage {
  url: string;
  alt_text: string;
  license: string;
  attribution: string;
  source_url: string;
}

export interface Variant {
  id: string;
  name: string;
  sku: string | null;
  status: string;
  weight_g: number | null;
  weight_basis: string | null;
  capacity_ml: number | null;
  specs: SpecRow[];
}

export interface ProductSummary {
  id: string;
  brand: BrandRef;
  name: string;
  display_name: string;
  category: CategoryRef;
  status: "active" | "discontinued";
  weight_g: number | null;
  weight_basis: string | null;
  weight_range_g: [number, number] | null;
  capacity_ml: number | null;
  variant_count: number;
  key_specs: SpecRow[];
  image: ProductImage | null;
}

export interface ProductDetail extends ProductSummary {
  model_number: string | null;
  model_year: string | null;
  official_url: string | null;
  verified_at: string | null;
  aliases: string[];
  specs: SpecRow[];
  variants: Variant[];
  sources: { name: string; url: string | null; verified_at: string | null }[];
}

export interface ProductPage {
  items: ProductSummary[];
  total: number;
  next_cursor: string | null;
}

export interface GearItem {
  id: string;
  kind: "catalog" | "custom";
  display_name: string;
  brand_name: string | null;
  category: CategoryRef;
  product: ProductSummary | null;
  variant: Variant | null;
  custom_name: string | null;
  custom_brand: string | null;
  custom_model: string | null;
  quantity: number;
  weight: {
    effective_g: number | null;
    source: "override" | "variant" | "product" | null;
    manufacturer_g: number | null;
    manufacturer_basis: string | null;
    override_g: number | null;
    override_unit: WeightUnit | null;
  };
  capacity: {
    effective_ml: number | null;
    source: "override" | "variant" | "product" | null;
    manufacturer_ml: number | null;
    override_ml: number | null;
  };
  custom_specs: SpecRow[];
  notes: string | null;
  condition: Condition | null;
  image_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface GearCollection {
  items: GearItem[];
  summary: {
    item_count: number;
    total_quantity: number;
    known_weight_g: number;
    items_missing_weight: number;
    weight_is_complete: boolean;
    categories_with_items: string[];
  };
}

export interface GearItemInput {
  client_request_id?: string;
  product_id?: string | null;
  variant_id?: string | null;
  category?: string | null;
  custom_name?: string | null;
  custom_brand?: string | null;
  custom_model?: string | null;
  quantity?: number;
  weight_override?: { value: string; unit: WeightUnit } | null;
  capacity_override?: { value: string; unit: VolumeUnit } | null;
  notes?: string | null;
  condition?: Condition | null;
  image_path?: string | null;
}

export const listCategories = (signal?: AbortSignal) =>
  apiFetch<GearCategory[]>("/api/gear/categories", { signal });

export const listBrands = (category?: string, signal?: AbortSignal) =>
  apiFetch<Brand[]>(
    `/api/gear/brands${category ? `?category=${encodeURIComponent(category)}` : ""}`,
    { signal },
  );

export function searchProducts(
  params: { q?: string; category?: string; brand?: string; cursor?: string | null; limit?: number },
  signal?: AbortSignal,
  filters: { max_weight_g?: number | null; min_capacity_ml?: number; max_capacity_ml?: number } = {},
) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value != null) search.set(key, String(value));
  }
  if (params.q) search.set("q", params.q);
  if (params.category) search.set("category", params.category);
  if (params.brand) search.set("brand", params.brand);
  if (params.cursor) search.set("cursor", params.cursor);
  search.set("limit", String(params.limit ?? 12));
  return apiFetch<ProductPage>(`/api/gear/products?${search}`, { signal });
}

export const getProduct = (id: string, signal?: AbortSignal) =>
  apiFetch<ProductDetail>(`/api/gear/products/${encodeURIComponent(id)}`, { signal });

export const listMyGear = (signal?: AbortSignal) =>
  apiFetch<GearCollection>("/api/me/gear", { auth: true, signal });

export const addMyGear = (input: GearItemInput) =>
  apiFetch<GearItem>("/api/me/gear", { method: "POST", body: input, auth: true });

export const updateMyGear = (id: string, input: GearItemInput) =>
  apiFetch<GearItem>(`/api/me/gear/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: input,
    auth: true,
  });

export const deleteMyGear = (id: string) =>
  apiFetch<void>(`/api/me/gear/${encodeURIComponent(id)}`, { method: "DELETE", auth: true });
