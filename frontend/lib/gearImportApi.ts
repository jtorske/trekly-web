import { apiFetch } from "./api";
import type { ConfirmRequest, ImportPreview } from "./lighterpackImport";

/** Reads a LighterPack CSV export and proposes matches. Saves nothing. */
export const previewImport = (csv: string) =>
  apiFetch<ImportPreview>("/api/me/gear/import/lighterpack", { method: "POST", body: { csv }, auth: true });

/** Adds the confirmed items. Retrying with the same import_id adds nothing twice. */
export const confirmImport = (request: ConfirmRequest) =>
  apiFetch<{ added: number; already_added: number }>("/api/me/gear/import/lighterpack/confirm", {
    method: "POST",
    body: request,
    auth: true,
  });
