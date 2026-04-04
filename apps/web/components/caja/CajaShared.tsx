"use client";

import React from "react";
import { C } from "@/lib/theme";

// ─── Types ───────────────────────────────────────────────────────────────────
export type Register = { id: number; name: string; is_active: boolean; has_open_session: boolean };
export type Movement = { id: number; type: "IN" | "OUT"; amount: string; description: string; created_by: string; created_at: string };
export type LiveSummary = {
  initial_amount: string; cash_sales: string; debit_sales: string; card_sales: string; transfer_sales: string; total_sales: string;
  cash_tips: string; movements_in: string; movements_out: string; expected_cash: string;
};
export type Session = {
  id: number; register_id: number; register_name: string; status: "OPEN" | "CLOSED";
  opened_by: string; opened_at: string; initial_amount: string;
  closed_at?: string | null; counted_cash?: string | null;
  expected_cash?: string | null; difference?: string | null; note?: string;
  movements?: Movement[];
  live?: LiveSummary;
};

// ─── Helpers ─────────────────────────────────────────────────────────────────
export function fmt(v: string | number) {
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? Math.round(n).toLocaleString("es-CL") : "0";
}
export function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ─── Btn ─────────────────────────────────────────────────────────────────────
export function Btn({ children, onClick, variant = "secondary", disabled, full }: {
  children: React.ReactNode; onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost"; disabled?: boolean; full?: boolean;
}) {
  const vs = {
    primary: { background: C.accent, color: "#fff", border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text, border: `1px solid ${C.borderMd}` },
    danger: { background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` },
    ghost: { background: "transparent", color: C.mid, border: "1px solid transparent" },
  }[variant];
  return (
    <button onClick={onClick} disabled={disabled} style={{
      ...vs, padding: "9px 18px", borderRadius: C.r, fontSize: 14, fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
      display: "inline-flex", alignItems: "center", gap: 6,
      width: full ? "100%" : undefined, justifyContent: full ? "center" : undefined,
      transition: "all 0.13s ease",
    }}>
      {children}
    </button>
  );
}

// ─── FlowRow ─────────────────────────────────────────────────────────────────
export function FlowRow({ label, amount, color }: { label: string; amount: string; color?: string }) {
  const n = Number(amount);
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0" }}>
      <span style={{ fontSize: 13, color: C.mid }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: color || C.text }}>
        {n >= 0 ? "+" : ""} ${fmt(Math.abs(n))}
      </span>
    </div>
  );
}
