"use client";

import React from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";

// ─── Types ───────────────────────────────────────────────────────────────────
export type IssueLine = {
  product_id: number;
  name: string;
  sku: string | null;
  on_hand: string;
  unit: string | null;
  qty: string;
  reason: string;
  note: string;
  reasonTouched: boolean;
};

export const REASONS = [
  { value: "USO_INTERNO", label: "Uso interno" },
  { value: "MERMA", label: "Merma" },
  { value: "VENCIDO", label: "Vencido" },
  { value: "OTRO", label: "Otro" },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────
function toNum(v: string | number | null | undefined): number {
  if (v == null) return NaN;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}
function fQty(v: string): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return n.toLocaleString("es-CL", { maximumFractionDigits: 3 });
}
function sanitizePos(v: string): string {
  const c = v.replace(/[^0-9.]/g, "");
  const p = c.split(".");
  return p.length <= 2 ? c : `${p[0]}.${p.slice(1).join("")}`;
}

function iS(extra?: React.CSSProperties): React.CSSProperties {
  return { width: "100%", height: 36, padding: "0 10px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, background: C.surface, ...extra };
}

function StockBadge({ val }: { val: string }) {
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

export function lineError(l: IssueLine): string | null {
  const q = toNum(l.qty);
  const oh = toNum(l.on_hand);
  if (l.qty.trim() && !isNaN(q)) {
    if (q <= 0) return "Debe ser > 0";
    if (q > oh) return "Stock insuficiente";
  }
  return null;
}

// ─── Search Dropdown ─────────────────────────────────────────────────────────
export type StockRow = { product_id: number; sku: string | null; name: string; on_hand: string; unit: string | null };

interface SearchDropdownProps {
  searchRef: React.RefObject<HTMLDivElement | null>;
  searchQ: string;
  setSearchQ: (v: string) => void;
  searchResults: StockRow[];
  searchLoading: boolean;
  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;
  lines: IssueLine[];
  addProduct: (row: StockRow) => void;
}

export function SalidasSearchDropdown({ searchRef, searchQ, setSearchQ, searchResults, searchLoading, searchOpen, setSearchOpen, lines, addProduct }: SearchDropdownProps) {
  return (
    <div ref={searchRef} style={{ position: "relative", marginBottom: 12 }}>
      <div style={{ position: "relative" }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
        <input
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          placeholder="Buscar producto por nombre o SKU..."
          style={{ ...iS({ paddingLeft: 34 }) }}
          onFocus={() => { if (searchResults.length) setSearchOpen(true); }}
        />
        {searchLoading && <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)" }}><Spinner size={14} /></div>}
      </div>

      {searchOpen && searchResults.length > 0 && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
          background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r,
          boxShadow: "0 8px 24px rgba(0,0,0,0.12)", maxHeight: 260, overflowY: "auto", marginTop: 4,
        }}>
          {searchResults.map(row => {
            const alreadyAdded = lines.some(l => l.product_id === row.product_id);
            return (
              <button
                key={row.product_id}
                onClick={() => addProduct(row)}
                style={{
                  display: "flex", alignItems: "center", gap: 10, width: "100%",
                  padding: "8px 12px", border: "none", cursor: "pointer", fontFamily: C.font,
                  fontSize: 13, color: alreadyAdded ? C.mute : C.text,
                  background: "transparent", textAlign: "left", transition: "background 0.1s",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = C.bg)}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {row.name}
                    {alreadyAdded && <span style={{ fontSize: 11, color: C.mute, marginLeft: 6 }}>(ya agregado)</span>}
                  </div>
                  {row.sku && <div style={{ fontSize: 11, color: C.mute }}>SKU: {row.sku}</div>}
                </div>
                <StockBadge val={row.on_hand} />
              </button>
            );
          })}
        </div>
      )}
      {searchOpen && searchQ.trim() && !searchLoading && searchResults.length === 0 && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
          background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r,
          boxShadow: "0 8px 24px rgba(0,0,0,0.12)", padding: "12px 16px", marginTop: 4,
          fontSize: 13, color: C.mute, textAlign: "center",
        }}>
          Sin resultados para &quot;{searchQ}&quot;
        </div>
      )}
    </div>
  );
}

// ─── Lines Table ─────────────────────────────────────────────────────────────
interface LinesTableProps {
  lines: IssueLine[];
  flashId: number | null;
  mob: boolean;
  updateLine: (idx: number, field: Partial<IssueLine>) => void;
  removeLine: (idx: number) => void;
}

export function SalidasLinesTable({ lines, flashId, mob, updateLine, removeLine }: LinesTableProps) {
  if (lines.length === 0) {
    return (
      <div style={{ padding: "32px 0", textAlign: "center", color: C.mute, fontSize: 13 }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={C.border} strokeWidth="1.5" strokeLinecap="round" style={{ marginBottom: 8 }}><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
        <div>Busca y agrega productos para registrar la salida</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {!mob && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 100px 130px 1fr 36px", gap: 8, padding: "6px 8px", fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: `1px solid ${C.border}` }}>
          <span>Producto</span>
          <span>Stock</span>
          <span>Cantidad</span>
          <span>Motivo</span>
          <span>Nota</span>
          <span />
        </div>
      )}

      {lines.map((line, idx) => {
        const err = lineError(line);
        const isFlashing = flashId === line.product_id;
        return (
          <div
            key={line.product_id}
            className={isFlashing ? "line-flash" : ""}
            style={{
              display: mob ? "flex" : "grid",
              flexDirection: mob ? "column" : undefined,
              gridTemplateColumns: mob ? undefined : "1fr 80px 100px 130px 1fr 36px",
              gap: 8, padding: "10px 8px", alignItems: mob ? undefined : "center",
              borderBottom: `1px solid ${C.border}`,
              background: err ? `${C.redBg}44` : "transparent",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{line.name}</div>
              {line.sku && <div style={{ fontSize: 11, color: C.mute }}>SKU: {line.sku}</div>}
            </div>

            {mob && <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, marginBottom: 2 }}>STOCK</div>}
            <StockBadge val={line.on_hand} />

            {mob && <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, marginTop: 6 }}>CANTIDAD{line.unit ? ` (${line.unit})` : ""}</div>}
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <input
                  value={line.qty}
                  onChange={e => updateLine(idx, { qty: sanitizePos(e.target.value) })}
                  inputMode="decimal"
                  placeholder="0"
                  style={{ ...iS({ fontFamily: C.mono, height: 32, fontSize: 13 }), borderColor: err ? C.red : C.border }}
                />
                {line.unit && !mob && (
                  <span style={{ fontSize: 11, fontWeight: 600, color: C.mute, whiteSpace: "nowrap" }}>{line.unit}</span>
                )}
              </div>
              {err && <div style={{ fontSize: 10, color: C.red, fontWeight: 600, marginTop: 2 }}>{err}</div>}
            </div>

            {mob && <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, marginTop: 6 }}>MOTIVO</div>}
            <select
              value={line.reason}
              onChange={e => updateLine(idx, { reason: e.target.value, reasonTouched: true })}
              style={{ ...iS({ height: 32, fontSize: 12 }) }}
            >
              {REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>

            {mob && <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, marginTop: 6 }}>NOTA</div>}
            <input
              value={line.note}
              onChange={e => updateLine(idx, { note: e.target.value })}
              placeholder="Opcional"
              style={{ ...iS({ height: 32, fontSize: 12 }) }}
            />

            <button
              onClick={() => removeLine(idx)}
              className="xb"
              style={{ width: 32, height: 32, borderRadius: C.r, border: `1px solid ${C.border}`, background: C.bg, color: C.mute, fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0, alignSelf: mob ? "flex-end" : undefined }}
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
