"use client";

import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";

// ─── Types ───────────────────────────────────────────────────────────────────
type Warehouse = { id: number; name: string; is_active: boolean };
type StockRow = { product_id: number; sku: string | null; name: string; on_hand: string; unit: string | null };
type IssueLine = {
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

const REASONS = [
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

// ─── Components ──────────────────────────────────────────────────────────────

type BtnV = "primary" | "secondary" | "ghost" | "danger" | "success";
function Btn({ children, onClick, variant = "secondary", disabled, size = "md", full }: { children: React.ReactNode; onClick?: () => void; variant?: BtnV; disabled?: boolean; size?: "sm" | "md" | "lg"; full?: boolean }) {
  const vs: Record<BtnV, React.CSSProperties> = {
    primary: { background: C.accent, color: "#fff", border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text, border: `1px solid ${C.borderMd}` },
    ghost: { background: "transparent", color: C.mid, border: "1px solid transparent" },
    danger: { background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` },
    success: { background: C.greenBg, color: C.green, border: `1px solid ${C.greenBd}` },
  };
  const h = size === "lg" ? 46 : size === "sm" ? 30 : 38;
  const px = size === "lg" ? "0 20px" : size === "sm" ? "0 10px" : "0 14px";
  const fs = size === "lg" ? 14 : size === "sm" ? 11 : 13;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="xb" style={{ ...vs[variant], display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, height: h, padding: px, borderRadius: C.r, fontSize: fs, fontWeight: 600, letterSpacing: "0.01em", whiteSpace: "nowrap", width: full ? "100%" : undefined }}>
      {children}
    </button>
  );
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

// ─── Main Page ───────────────────────────────────────────────────────────────
const PAGE_CSS = `
.srow{transition:background 0.1s ease}.srow:hover{background:#FAFAFA}
@keyframes flash{0%{background:#FEF9C3}100%{background:transparent}}
.line-flash{animation:flash 1s ease}
`;

export default function SalidasPage() {
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();
  const router = useRouter();

  // Boot state
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId, setWarehouseId] = useState<number | null>(null);
  const [bootErr, setBootErr] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  // Global config
  const [globalReason, setGlobalReason] = useState("USO_INTERNO");
  const [globalNote, setGlobalNote] = useState("");

  // Lines
  const [lines, setLines] = useState<IssueLine[]>([]);
  const [flashId, setFlashId] = useState<number | null>(null);

  // Search
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<StockRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Submit
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0, errors: [] as string[] });
  const [submitDone, setSubmitDone] = useState(false);

  // ─── Boot ──────────────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      setBooting(true);
      try {
        const me = (await apiFetch("/core/me/")) as Me;
        if (!me?.tenant_id) { setBootErr("Tu usuario no tiene tenant asignado."); return; }
        const whs = (await apiFetch("/core/warehouses/")) as Warehouse[];
        const list = Array.isArray(whs) ? whs : [];
        const active = list.filter(w => w.is_active);
        setWarehouses(active);
        if (!active.length) { setBootErr("No tienes bodegas activas."); return; }
        const preferred = me.default_warehouse_id && active.some(w => w.id === me.default_warehouse_id)
          ? me.default_warehouse_id : active[0].id;
        setWarehouseId(preferred);
      } catch (e: any) { setBootErr(e?.message ?? "No se pudo cargar configuración."); }
      finally { setBooting(false); }
    })();
  }, []);

  // ─── Search ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!searchQ.trim() || !warehouseId) {
      setSearchResults([]);
      setSearchOpen(false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const data = await apiFetch(`/inventory/stock/?warehouse_id=${warehouseId}&q=${encodeURIComponent(searchQ.trim())}&page_size=10`);
        const results = Array.isArray(data) ? data : data?.results ?? [];
        setSearchResults(results);
        setSearchOpen(true);
      } catch { setSearchResults([]); }
      finally { setSearchLoading(false); }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [searchQ, warehouseId]);

  // Close search on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setSearchOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // ─── Handlers ──────────────────────────────────────────────────────────
  function addProduct(row: StockRow) {
    // Check duplicate
    const existing = lines.find(l => l.product_id === row.product_id);
    if (existing) {
      setFlashId(row.product_id);
      setTimeout(() => setFlashId(null), 1000);
      setSearchOpen(false);
      setSearchQ("");
      return;
    }
    setLines(prev => [...prev, {
      product_id: row.product_id,
      name: row.name,
      sku: row.sku,
      on_hand: row.on_hand,
      unit: row.unit ?? null,
      qty: "",
      reason: globalReason,
      note: "",
      reasonTouched: false,
    }]);
    setSearchOpen(false);
    setSearchQ("");
  }

  function updateLine(idx: number, field: Partial<IssueLine>) {
    setLines(prev => prev.map((l, i) => i === idx ? { ...l, ...field } : l));
  }

  function removeLine(idx: number) {
    setLines(prev => prev.filter((_, i) => i !== idx));
  }

  function handleGlobalReasonChange(reason: string) {
    setGlobalReason(reason);
    setLines(prev => prev.map(l => l.reasonTouched ? l : { ...l, reason }));
  }

  function handleWarehouseChange(whId: number) {
    setWarehouseId(whId);
    setLines([]);
    setSearchQ("");
    setSearchResults([]);
  }

  // ─── Validation ────────────────────────────────────────────────────────
  const validation = useMemo(() => {
    let totalQty = 0;
    let invalidCount = 0;
    for (const l of lines) {
      const q = toNum(l.qty);
      const oh = toNum(l.on_hand);
      if (isNaN(q) || q <= 0) { invalidCount++; continue; }
      if (q > oh) { invalidCount++; continue; }
      totalQty += q;
    }
    return {
      totalQty,
      invalidCount,
      canSubmit: lines.length > 0 && invalidCount === 0 && !!warehouseId && lines.every(l => { const q = toNum(l.qty); return !isNaN(q) && q > 0; }),
    };
  }, [lines, warehouseId]);

  // ─── Submit ────────────────────────────────────────────────────────────
  async function handleSubmit() {
    if (!validation.canSubmit || submitting) return;
    setSubmitting(true);
    setSubmitDone(false);
    const total = lines.length;
    const errors: string[] = [];
    let done = 0;
    setProgress({ done: 0, total, errors: [] });

    const succeeded: number[] = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      try {
        await apiFetch("/inventory/issue/", {
          method: "POST",
          body: JSON.stringify({
            warehouse_id: warehouseId,
            product_id: line.product_id,
            qty: String(toNum(line.qty)),
            reason: line.reason,
            note: line.note || globalNote || "Salida masiva",
          }),
        });
        succeeded.push(i);
        done++;
      } catch (e: any) {
        errors.push(`${line.name}: ${e?.message ?? "Error desconocido"}`);
      }
      setProgress({ done: done, total, errors: [...errors] });
    }

    if (errors.length === 0) {
      // All succeeded — redirect to stock
      router.push("/dashboard/inventory/stock");
    } else {
      // Partial failure — remove succeeded, keep failed
      setLines(prev => prev.filter((_, i) => !succeeded.includes(i)));
      setSubmitDone(true);
      setSubmitting(false);
    }
  }

  // ─── Line validation helper ────────────────────────────────────────────
  function lineError(l: IssueLine): string | null {
    const q = toNum(l.qty);
    const oh = toNum(l.on_hand);
    if (l.qty.trim() && !isNaN(q)) {
      if (q <= 0) return "Debe ser > 0";
      if (q > oh) return "Stock insuficiente";
    }
    return null;
  }

  const whName = warehouses.find(w => w.id === warehouseId)?.name ?? "";

  // ─── Render ────────────────────────────────────────────────────────────
  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "16px 12px" : "24px 28px" }}>

      {/* HEADER */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <div style={{ width: 4, height: 26, background: C.red, borderRadius: 2 }} />
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: "-0.04em" }}>Salida de stock</h1>
            {whName && <span style={{ fontSize: 12, color: C.mute, fontWeight: 500, padding: "2px 8px", borderRadius: 99, border: `1px solid ${C.border}`, background: C.surface }}>{whName}</span>}
          </div>
          <p style={{ margin: 0, fontSize: 13, color: C.mute, paddingLeft: 14 }}>Registra salidas por uso interno, merma, vencimiento u otro motivo</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn variant="ghost" onClick={() => router.push("/dashboard/inventory/stock")}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
            Volver
          </Btn>
          <Btn variant="danger" onClick={handleSubmit} disabled={!validation.canSubmit || submitting}>
            {submitting ? <><Spinner size={13} /> Procesando...</> : (
              <>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                Confirmar salida
              </>
            )}
          </Btn>
        </div>
      </div>

      {/* Boot error */}
      {bootErr && (
        <div style={{ padding: "11px 14px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13, fontWeight: 600 }}>{bootErr}</div>
      )}

      {booting && <div style={{ textAlign: "center", padding: 40, color: C.mute }}><Spinner size={24} /></div>}

      {!booting && !bootErr && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 280px", gap: 20, alignItems: "start" }}>

          {/* LEFT COLUMN */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Global config card */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", boxShadow: C.sh }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 12 }}>Configuración</div>
              <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr 1fr", gap: 12 }}>
                {/* Warehouse */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>Bodega</div>
                  {warehouses.length > 1 ? (
                    <select value={warehouseId ?? ""} onChange={e => handleWarehouseChange(Number(e.target.value))} style={iS({ height: 36 })}>
                      {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                    </select>
                  ) : (
                    <div style={{ ...iS(), display: "flex", alignItems: "center", color: C.mid, fontSize: 13 }}>{whName}</div>
                  )}
                </div>
                {/* Global reason */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>Motivo general</div>
                  <select value={globalReason} onChange={e => handleGlobalReasonChange(e.target.value)} style={iS({ height: 36 })}>
                    {REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                </div>
                {/* Global note */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>Nota</div>
                  <input value={globalNote} onChange={e => setGlobalNote(e.target.value)} placeholder="Ej: Reunión directorio" style={iS()} />
                </div>
              </div>
            </div>

            {/* Products card */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", boxShadow: C.sh }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Productos a egresar</div>
                <span style={{ fontSize: 12, color: C.mute }}>{lines.length} línea{lines.length !== 1 ? "s" : ""}</span>
              </div>

              {/* Search */}
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

                {/* Search dropdown */}
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
                    Sin resultados para "{searchQ}"
                  </div>
                )}
              </div>

              {/* Lines table */}
              {lines.length === 0 ? (
                <div style={{ padding: "32px 0", textAlign: "center", color: C.mute, fontSize: 13 }}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={C.border} strokeWidth="1.5" strokeLinecap="round" style={{ marginBottom: 8 }}><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
                  <div>Busca y agrega productos para registrar la salida</div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  {/* Header row (desktop) */}
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
                        {/* Product name */}
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{line.name}</div>
                          {line.sku && <div style={{ fontSize: 11, color: C.mute }}>SKU: {line.sku}</div>}
                        </div>

                        {/* Stock */}
                        {mob && <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, marginBottom: 2 }}>STOCK</div>}
                        <StockBadge val={line.on_hand} />

                        {/* Qty */}
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

                        {/* Reason */}
                        {mob && <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, marginTop: 6 }}>MOTIVO</div>}
                        <select
                          value={line.reason}
                          onChange={e => updateLine(idx, { reason: e.target.value, reasonTouched: true })}
                          style={{ ...iS({ height: 32, fontSize: 12 }) }}
                        >
                          {REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                        </select>

                        {/* Note */}
                        {mob && <div style={{ fontSize: 11, fontWeight: 700, color: C.mute, marginTop: 6 }}>NOTA</div>}
                        <input
                          value={line.note}
                          onChange={e => updateLine(idx, { note: e.target.value })}
                          placeholder="Opcional"
                          style={{ ...iS({ height: 32, fontSize: 12 }) }}
                        />

                        {/* Remove */}
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
              )}
            </div>

            {/* Submit errors */}
            {submitDone && progress.errors.length > 0 && (
              <div style={{ padding: "12px 16px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>
                  {progress.done} de {progress.total} salida(s) procesadas. Errores:
                </div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {progress.errors.map((e, i) => <li key={i} style={{ marginBottom: 2 }}>{e}</li>)}
                </ul>
                <div style={{ marginTop: 10 }}>
                  <Btn variant="danger" size="sm" onClick={handleSubmit}>Reintentar fallidos</Btn>
                </div>
              </div>
            )}
          </div>

          {/* RIGHT COLUMN — Summary */}
          <div style={{ position: mob ? "relative" : "sticky", top: mob ? undefined : 24 }}>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", boxShadow: C.sh }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 14 }}>Resumen</div>

              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 13, color: C.mute }}>Productos</span>
                  <span style={{ fontSize: 14, fontWeight: 700, fontFamily: C.mono }}>{lines.length}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 13, color: C.mute }}>Unidades a egresar</span>
                  <span style={{ fontSize: 14, fontWeight: 700, fontFamily: C.mono, color: validation.totalQty > 0 ? C.red : C.text }}>
                    {validation.totalQty > 0 ? `- ${validation.totalQty.toLocaleString("es-CL", { maximumFractionDigits: 3 })}` : "0"}
                  </span>
                </div>
                {validation.invalidCount > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 13, color: C.red, fontWeight: 600 }}>Con errores</span>
                    <span style={{ fontSize: 14, fontWeight: 700, fontFamily: C.mono, color: C.red }}>{validation.invalidCount}</span>
                  </div>
                )}
                <div style={{ height: 1, background: C.border }} />
                <div style={{ fontSize: 12, color: C.mute }}>
                  Motivo: <span style={{ fontWeight: 600, color: C.mid }}>{REASONS.find(r => r.value === globalReason)?.label}</span>
                </div>
                {globalNote && (
                  <div style={{ fontSize: 12, color: C.mute }}>
                    Nota: <span style={{ fontWeight: 600, color: C.mid }}>{globalNote}</span>
                  </div>
                )}
              </div>

              <div style={{ marginTop: 16 }}>
                <Btn variant="danger" full onClick={handleSubmit} disabled={!validation.canSubmit || submitting} size="lg">
                  {submitting ? <><Spinner size={14} /> Procesando...</> : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                      Confirmar salida ({lines.length})
                    </>
                  )}
                </Btn>
              </div>

              {lines.length > 0 && !validation.canSubmit && !submitting && (
                <div style={{ fontSize: 11, color: C.amber, fontWeight: 600, marginTop: 8, textAlign: "center" }}>
                  Completa las cantidades de todos los productos
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Progress overlay */}
      {submitting && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "grid", placeItems: "center", zIndex: 100 }}>
          <div style={{ background: C.surface, borderRadius: C.rLg, padding: "28px 36px", textAlign: "center", boxShadow: C.shLg, minWidth: 280 }}>
            <Spinner size={28} />
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginTop: 14 }}>Procesando salida...</div>
            <div style={{ fontSize: 13, color: C.mute, marginTop: 6 }}>{progress.done} de {progress.total} productos</div>
            <div style={{ width: "100%", height: 6, background: C.bg, borderRadius: 3, marginTop: 12, overflow: "hidden" }}>
              <div style={{ height: "100%", background: C.accent, borderRadius: 3, transition: "width 0.3s ease", width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
