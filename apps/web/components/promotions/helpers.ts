import { C } from "@/lib/theme";
import { formatCLP } from "@/lib/format";

export function formatDate(iso: string) {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  return d.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDatetimeLocal(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function discountLabel(type: "percentage" | "fixed", value: string) {
  if (type === "percentage") return `${value}% OFF`;
  return `$${formatCLP(value)} fijo`;
}

export function promoPrice(price: string, type: "percentage" | "fixed", value: string, override?: string | null) {
  const p = Number(price);
  const v = Number(override || value);
  if (Number.isNaN(p) || Number.isNaN(v) || v <= 0) return "\u2014";
  if (type === "percentage") return formatCLP(Math.round(p * (1 - v / 100)));
  return formatCLP(v);
}

export const STATUS_MAP: Record<string, { label: string; bg: string; bd: string; c: string }> = {
  active:    { label: "Activa",     bg: C.greenBg,  bd: C.greenBd,  c: C.green },
  scheduled: { label: "Programada", bg: C.skyBg,    bd: C.skyBd,    c: C.sky   },
  expired:   { label: "Expirada",   bg: "#F4F4F5",  bd: C.border,   c: C.mid   },
  inactive:  { label: "Inactiva",   bg: C.redBg,    bd: C.redBd,    c: C.red   },
};
