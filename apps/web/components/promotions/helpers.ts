import { C } from "@/lib/theme";
import { formatCLP } from "@/lib/format";
import type { DiscountType } from "./types";

export function formatDate(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDatetimeLocal(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function discountLabel(type: DiscountType, value: string) {
  if (type === "pct") {
    // El backend guarda "30.00" pero Mario quiere ver "30% OFF" (sin
    // decimales innecesarios). parseFloat → toString quita los ceros
    // trailing automáticamente y conserva los decimales reales:
    //   "30.00"  → "30"
    //   "30.50"  → "30.5"
    //   "12.345" → "12.345"
    const n = parseFloat(value);
    const display = Number.isFinite(n) ? n.toString() : value;
    return `${display}% OFF`;
  }
  return `$${formatCLP(value)} fijo`;
}

export function promoPrice(price: string, type: DiscountType, value: string, override?: string | null) {
  const p = Number(price);
  const v = Number(override || value);
  if (Number.isNaN(p) || Number.isNaN(v) || v <= 0) return "—";
  if (type === "pct") return formatCLP(Math.round(p * (1 - v / 100)));
  return formatCLP(v);
}

export const STATUS_MAP: Record<string, { label: string; bg: string; bd: string; c: string }> = {
  active:    { label: "Activa",     bg: C.greenBg,  bd: C.greenBd,  c: C.green },
  scheduled: { label: "Programada", bg: C.skyBg,    bd: C.skyBd,    c: C.sky   },
  expired:   { label: "Expirada",   bg: "#F4F4F5",  bd: C.border,   c: C.mid   },
  inactive:  { label: "Inactiva",   bg: C.redBg,    bd: C.redBd,    c: C.red   },
};
