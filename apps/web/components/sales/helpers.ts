export function toNum(v: string | number | null | undefined): number {
  if (v == null) return 0;
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

export function fCLP(v: string | number | null | undefined): string {
  return Math.round(toNum(v)).toLocaleString("es-CL");
}

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}

export function fDateTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-CL", { day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit" });
}

export function fDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-CL", { day:"2-digit", month:"2-digit", year:"numeric" });
}

export function profitPct(profit: string, total: string): number | null {
  const t = toNum(total); const p = toNum(profit);
  if (t === 0) return null;
  return Math.round((p / t) * 100);
}
