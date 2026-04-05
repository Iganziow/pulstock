"use client";

import React from "react";
import { C } from "@/lib/theme";
import { Btn, Modal } from "@/components/ui";
export { Btn, Modal };

export type Warehouse = { id: number; name: string; is_active: boolean; warehouse_type?: string };
export type StockRow = { product_id: number; sku: string | null; name: string; category: string | null; barcode: string | null; on_hand: string; avg_cost?: string | null };

export function toNum(v: string | number | null | undefined): number {
  if (v == null) return NaN;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}
export function fQty(v: string): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return n.toLocaleString("es-CL", { maximumFractionDigits: 3 });
}
export function sanitizePos(v: string): string {
  const c = v.replace(/[^0-9.]/g, "");
  const p = c.split(".");
  return p.length <= 2 ? c : `${p[0]}.${p.slice(1).join("")}`;
}
export function sanitizeDelta(v: string): string {
  let c = v.replace(/[^0-9.\-]/g, "");
  c = c.replace(/(?!^)-/g, "");
  const p = c.split(".");
  return p.length <= 2 ? c : `${p[0]}.${p.slice(1).join("")}`;
}

export function iS(extra?: React.CSSProperties): React.CSSProperties {
  return { width: "100%", height: 36, padding: "0 10px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, background: C.surface, ...extra };
}

export function StockBadge({ val }: { val: string }) {
  const n = toNum(val);
  const low = !isNaN(n) && n <= 5;
  const zero = !isNaN(n) && n <= 0;
  const color = zero ? C.red : low ? C.amber : C.green;
  const bg = zero ? C.redBg : low ? C.amberBg : C.greenBg;
  const bd = zero ? C.redBd : low ? C.amberBd : C.greenBd;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 99, fontSize: 12, fontWeight: 700, border: `1px solid ${bd}`, background: bg, color, fontVariantNumeric: "tabular-nums", fontFamily: C.mono }}>
      {fQty(val)}
    </span>
  );
}

export function ProductCard({ row }: { row: StockRow }) {
  return (
    <div style={{ padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.bg, marginBottom: 14 }}>
      <div style={{ fontWeight: 700, fontSize: 14 }}>{row.name}</div>
      <div style={{ display: "flex", gap: 16, marginTop: 4, fontSize: 12, color: C.mute }}>
        {row.sku && <span>SKU: <span style={{ fontFamily: C.mono, color: C.mid }}>{row.sku}</span></span>}
        {row.barcode && <span>Barcode: <span style={{ fontFamily: C.mono, color: C.mid }}>{row.barcode}</span></span>}
        <span>Stock: <span style={{ fontWeight: 700, color: C.text, fontFamily: C.mono }}>{fQty(row.on_hand)}</span></span>
      </div>
    </div>
  );
}

export function FieldGroup({ label, children, hint, err }: { label: string; children: React.ReactNode; hint?: string; err?: string | null }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</label>
      {children}
      {hint && !err && <div style={{ fontSize: 11, color: C.mute }}>{hint}</div>}
      {err && <div style={{ fontSize: 11, color: C.red, fontWeight: 600 }}>{err}</div>}
    </div>
  );
}

export function ErrBanner({ msg, onClose }: { msg: string; onClose: () => void }) {
  return (
    <div style={{ padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13, display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /></svg>
      <span style={{ flex: 1 }}>{msg}</span>
      <button type="button" aria-label="Cerrar" onClick={onClose} className="xb" style={{ background: "none", border: "none", color: C.red, fontSize: 15, cursor: "pointer", padding: 0, lineHeight: 1 }}>✕</button>
    </div>
  );
}

export function OkBanner({ msg }: { msg: string }) {
  return (
    <div style={{ padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.greenBd}`, background: C.greenBg, color: C.green, fontSize: 13, display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ flexShrink: 0 }}><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
      {msg}
    </div>
  );
}

export function PreviewRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span style={{ fontSize: 12, color: C.mute }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 700, fontVariantNumeric: "tabular-nums", fontFamily: C.mono, color: highlight ? C.accent : C.text }}>{value}</span>
    </div>
  );
}
