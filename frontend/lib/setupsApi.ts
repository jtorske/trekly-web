import { apiFetch } from "./api";
import type { GearItem } from "./gearApi";

export interface GearSetup {
  id: string;
  name: string;
  description: string | null;
  items: GearItem[];
  item_count: number;
  known_weight_g: number;
  items_missing_weight: number;
  created_at: string;
  updated_at: string;
}

export interface SetupInput {
  name?: string;
  description?: string | null;
  item_ids?: string[];
}

export const listSetups = (signal?: AbortSignal) =>
  apiFetch<GearSetup[]>("/api/me/setups", { auth: true, signal });

export const createSetup = (input: SetupInput) =>
  apiFetch<GearSetup>("/api/me/setups", { method: "POST", body: input, auth: true });

export const updateSetup = (id: string, input: SetupInput) =>
  apiFetch<GearSetup>(`/api/me/setups/${encodeURIComponent(id)}`, { method: "PATCH", body: input, auth: true });

export const deleteSetup = (id: string) =>
  apiFetch<void>(`/api/me/setups/${encodeURIComponent(id)}`, { method: "DELETE", auth: true });
