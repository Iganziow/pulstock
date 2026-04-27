"use client";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
export { Btn, Spinner };

/* ── Settings-specific shared types ── */

export type Tenant = {
  id: number; name: string; slug: string; legal_name: string; rut: string; giro: string;
  address: string; city: string; comuna: string; phone: string; email: string;
  website: string; logo_url: string; primary_color: string;
  receipt_header: string; receipt_footer: string; receipt_show_logo: boolean; receipt_show_rut: boolean;
  currency: string; timezone: string; tax_rate: string; created_at: string;
};

export type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
export type Store = { id: number; name: string; code: string; is_active: boolean; warehouses: Warehouse[] };
export type StoreAccess = { store_id: number; store_name: string };
export type User = {
  id: number; username: string; email: string; first_name: string; last_name: string;
  role: string; role_label: string; is_active: boolean; active_store_id: number | null;
  store_access: StoreAccess[];
  date_joined: string; last_login: string | null;
};

export type Tab = "cuenta" | "empresa" | "boleta" | "tiendas" | "usuarios" | "alertas" | "impresoras" | "estaciones" | "plan";

export const ROLES = [
  { value: "owner", label: "Dueño/Gerente", desc: "Acceso total al sistema", color: C.accent, bg: C.accentBg, bd: C.accentBd },
  { value: "manager", label: "Administrador", desc: "Todo excepto configuración", color: C.amber, bg: C.amberBg, bd: C.amberBd },
  { value: "cashier", label: "Caja/Garzón", desc: "Punto de venta y catálogo", color: C.green, bg: C.greenBg, bd: C.greenBd },
  { value: "inventory", label: "Inventario", desc: "Stock, compras y catálogo", color: "#EA580C", bg: "#FFF7ED", bd: "#FDBA74" },
];

/* ── Inline style constants (settings-specific) ── */

export const iS: React.CSSProperties = {
  width: "100%", padding: "9px 12px", border: `1.5px solid ${C.border}`,
  borderRadius: 8, fontSize: 13, fontFamily: "'DM Sans',system-ui,sans-serif",
  background: C.surface, outline: "none", boxSizing: "border-box" as const,
  color: "#18181B", transition: "border-color .15s",
};
export const FL: React.CSSProperties = { display: "flex", flexDirection: "column" as const, gap: 4 };

/* ── Settings-specific UI components ── */

export function Label({ children, req }: { children: React.ReactNode; req?: boolean }) {
  return <label style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: ".06em" }}>{children}{req && <span style={{ color: C.red }}> *</span>}</label>;
}

export function Hint({ children }: { children: React.ReactNode }) {
  return <span style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>{children}</span>;
}

export function SectionHeader({ icon, title, desc }: { icon: string; title: string; desc?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 20 }}>
      <div style={{ fontSize: 22, flexShrink: 0 }}>{icon}</div>
      <div>
        <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-.02em" }}>{title}</div>
        {desc && <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>{desc}</div>}
      </div>
    </div>
  );
}

export function Divider() {
  return <div style={{ borderTop: `1px solid ${C.border}`, margin: "16px 0" }} />;
}

export function Card({ children, style: s, padding }: { children: React.ReactNode; style?: React.CSSProperties; padding?: number }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: padding ?? 22, boxShadow: C.sh, ...s }}>
      {children}
    </div>
  );
}
