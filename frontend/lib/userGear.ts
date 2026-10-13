import type { GearCategory } from "@/app/gear/gearCatalog";
import { getSupabaseClient } from "./supabaseClient";

export interface UserGearItem {
  id: string;
  category: GearCategory;
  slot: string | null;
  name: string;
  brand: string | null;
  model: string | null;
  weight_g: number | null;
  quantity: number;
  gear_item_id: string | null;
  created_at: string;
}

export type UserGearInput = Omit<UserGearItem, "id" | "created_at">;

export interface CatalogGearItem {
  id: string;
  name: string;
  category: string;
  weight_g: number | null;
}

const COLUMNS =
  "id, category, slot, name, brand, model, weight_g, quantity, gear_item_id, created_at";

// user_gear rows are protected by row-level security, so these queries only
// ever see or change the signed-in user's own gear.

export async function listUserGear(): Promise<UserGearItem[]> {
  const { data, error } = await getSupabaseClient()
    .from("user_gear")
    .select(COLUMNS)
    .order("created_at");
  if (error) throw new Error(error.message);
  return data as UserGearItem[];
}

export async function createUserGear(input: UserGearInput): Promise<UserGearItem> {
  const { data, error } = await getSupabaseClient()
    .from("user_gear")
    .insert(input)
    .select(COLUMNS)
    .single();
  if (error) throw new Error(error.message);
  return data as UserGearItem;
}

export async function updateUserGear(
  id: string,
  input: UserGearInput,
): Promise<UserGearItem> {
  const { data, error } = await getSupabaseClient()
    .from("user_gear")
    .update({ ...input, updated_at: new Date().toISOString() })
    .eq("id", id)
    .select(COLUMNS)
    .single();
  if (error) throw new Error(error.message);
  return data as UserGearItem;
}

export async function deleteUserGear(id: string): Promise<void> {
  const { error } = await getSupabaseClient().from("user_gear").delete().eq("id", id);
  if (error) throw new Error(error.message);
}

export async function searchGearCatalog(query: string): Promise<CatalogGearItem[]> {
  const escaped = query.replace(/[%_\\]/g, (char) => `\\${char}`);
  const { data, error } = await getSupabaseClient()
    .from("gear_items")
    .select("id, name, category, weight_g")
    .ilike("name", `%${escaped}%`)
    .order("name")
    .limit(8);
  if (error) throw new Error(error.message);
  return data as CatalogGearItem[];
}
