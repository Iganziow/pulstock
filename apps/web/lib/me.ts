import { apiFetch } from "@/lib/api";

/**
 * Matches the response shape of GET /api/core/me/
 * Single source of truth — do NOT redefine Me locally in pages.
 */
export type Me = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  tenant_id: number;
  tenant_name: string;
  active_store_id: number | null;
  default_warehouse_id: number | null;
  role: string;
  role_label: string;
  permissions: Record<string, boolean>;
};

export async function fetchMe(): Promise<Me> {
  return apiFetch("/core/me/");
}
