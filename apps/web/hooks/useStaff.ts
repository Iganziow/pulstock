"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

export type StaffMember = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  role: string;
  display_name: string;
};

// Cache module-level — el staff de un local cambia muy poco (un nuevo
// garzon cada varios dias). Re-fetcheamos cada 5 min para no congelar la
// lista para siempre, pero entre eso reusamos el cache para evitar pegarle
// a /core/staff/ cada vez que se abre un modal o se renderiza un filtro.
const cache: Record<string, { data: StaffMember[]; ts: number }> = {};
const TTL_MS = 5 * 60 * 1000;

export function useStaff(storeId?: number | null): {
  staff: StaffMember[];
  loading: boolean;
  error: string;
  refetch: () => Promise<void>;
} {
  const key = storeId ? `s${storeId}` : "all";
  const [staff, setStaff] = useState<StaffMember[]>(() => cache[key]?.data || []);
  const [loading, setLoading] = useState(!cache[key]);
  const [error, setError] = useState("");

  async function load() {
    const cached = cache[key];
    if (cached && Date.now() - cached.ts < TTL_MS) {
      setStaff(cached.data);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const qs = storeId ? `?store_id=${storeId}` : "";
      const data = await apiFetch(`/core/staff/${qs}`);
      const list = Array.isArray(data) ? data : [];
      cache[key] = { data: list, ts: Date.now() };
      setStaff(list);
      setError("");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al cargar staff";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  return { staff, loading, error, refetch: load };
}
