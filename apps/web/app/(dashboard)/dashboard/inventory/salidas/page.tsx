"use client";

import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";
import {
  SalidasSearchDropdown,
  SalidasLinesTable,
  REASONS,
  lineError,
  type IssueLine,
  type StockRow,
} from "@/components/inventory/SalidasLinesTable";
import { SalidasSummary, SalidasProgressOverlay } from "@/components/inventory/SalidasSummary";

// ─── Types ───────────────────────────────────────────────────────────────────
type Warehouse = { id: number; name: string; is_active: boolean };

function toNum(v: string | number | null | undefined): number {
  if (v == null) return NaN;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

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

  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId, setWarehouseId] = useState<number | null>(null);
  const [bootErr, setBootErr] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [globalReason, setGlobalReason] = useState("USO_INTERNO");
  const [globalNote, setGlobalNote] = useState("");
  const [lines, setLines] = useState<IssueLine[]>([]);
  const [flashId, setFlashId] = useState<number | null>(null);
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<StockRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
    if (!searchQ.trim() || !warehouseId) { setSearchResults([]); setSearchOpen(false); return; }
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

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setSearchOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // ─── Handlers ──────────────────────────────────────────────────────────
  function addProduct(row: StockRow) {
    if (lines.find(l => l.product_id === row.product_id)) {
      setFlashId(row.product_id);
      setTimeout(() => setFlashId(null), 1000);
      setSearchOpen(false); setSearchQ(""); return;
    }
    setLines(prev => [...prev, { product_id: row.product_id, name: row.name, sku: row.sku, on_hand: row.on_hand, unit: row.unit ?? null, qty: "", reason: globalReason, note: "", reasonTouched: false }]);
    setSearchOpen(false); setSearchQ("");
  }

  function updateLine(idx: number, field: Partial<IssueLine>) { setLines(prev => prev.map((l, i) => i === idx ? { ...l, ...field } : l)); }
  function removeLine(idx: number) { setLines(prev => prev.filter((_, i) => i !== idx)); }
  function handleGlobalReasonChange(reason: string) { setGlobalReason(reason); setLines(prev => prev.map(l => l.reasonTouched ? l : { ...l, reason })); }
  function handleWarehouseChange(whId: number) { setWarehouseId(whId); setLines([]); setSearchQ(""); setSearchResults([]); }

  const validation = useMemo(() => {
    let totalQty = 0; let invalidCount = 0;
    for (const l of lines) {
      const q = toNum(l.qty); const oh = toNum(l.on_hand);
      if (isNaN(q) || q <= 0) { invalidCount++; continue; }
      if (q > oh) { invalidCount++; continue; }
      totalQty += q;
    }
    return { totalQty, invalidCount, canSubmit: lines.length > 0 && invalidCount === 0 && !!warehouseId && lines.every(l => { const q = toNum(l.qty); return !isNaN(q) && q > 0; }) };
  }, [lines, warehouseId]);

  async function handleSubmit() {
    if (!validation.canSubmit || submitting) return;
    setSubmitting(true); setSubmitDone(false);
    const total = lines.length; const errors: string[] = []; let done = 0;
    setProgress({ done: 0, total, errors: [] });
    const succeeded: number[] = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      try {
        await apiFetch("/inventory/issue/", { method: "POST", body: JSON.stringify({ warehouse_id: warehouseId, product_id: line.product_id, qty: String(toNum(line.qty)), reason: line.reason, note: line.note || globalNote || "Salida masiva" }) });
        succeeded.push(i); done++;
      } catch (e: any) { errors.push(`${line.name}: ${e?.message ?? "Error desconocido"}`); }
      setProgress({ done, total, errors: [...errors] });
    }
    if (errors.length === 0) { router.push("/dashboard/inventory/stock"); }
    else { setLines(prev => prev.filter((_, i) => !succeeded.includes(i))); setSubmitDone(true); setSubmitting(false); }
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
              <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>Confirmar salida</>
            )}
          </Btn>
        </div>
      </div>

      {bootErr && <div style={{ padding: "11px 14px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13, fontWeight: 600 }}>{bootErr}</div>}
      {booting && <div style={{ textAlign: "center", padding: 40, color: C.mute }}><Spinner size={24} /></div>}

      {!booting && !bootErr && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 280px", gap: 20, alignItems: "start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Global config card */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", boxShadow: C.sh }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 12 }}>Configuraci&oacute;n</div>
              <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr 1fr", gap: 12 }}>
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
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>Motivo general</div>
                  <select value={globalReason} onChange={e => handleGlobalReasonChange(e.target.value)} style={iS({ height: 36 })}>
                    {REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C.mid, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>Nota</div>
                  <input value={globalNote} onChange={e => setGlobalNote(e.target.value)} placeholder="Ej: Reuni&oacute;n directorio" style={iS()} />
                </div>
              </div>
            </div>

            {/* Products card */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", boxShadow: C.sh }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>Productos a egresar</div>
                <span style={{ fontSize: 12, color: C.mute }}>{lines.length} l&iacute;nea{lines.length !== 1 ? "s" : ""}</span>
              </div>
              <SalidasSearchDropdown searchRef={searchRef} searchQ={searchQ} setSearchQ={setSearchQ} searchResults={searchResults} searchLoading={searchLoading} searchOpen={searchOpen} setSearchOpen={setSearchOpen} lines={lines} addProduct={addProduct} />
              <SalidasLinesTable lines={lines} flashId={flashId} mob={mob} updateLine={updateLine} removeLine={removeLine} />
            </div>

            {/* Submit errors */}
            {submitDone && progress.errors.length > 0 && (
              <div style={{ padding: "12px 16px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>{progress.done} de {progress.total} salida(s) procesadas. Errores:</div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {progress.errors.map((e, i) => <li key={i} style={{ marginBottom: 2 }}>{e}</li>)}
                </ul>
                <div style={{ marginTop: 10 }}><Btn variant="danger" size="sm" onClick={handleSubmit}>Reintentar fallidos</Btn></div>
              </div>
            )}
          </div>

          <SalidasSummary mob={mob} linesCount={lines.length} totalQty={validation.totalQty} invalidCount={validation.invalidCount} canSubmit={validation.canSubmit} submitting={submitting} globalReason={globalReason} globalNote={globalNote} onSubmit={handleSubmit} />
        </div>
      )}

      <SalidasProgressOverlay submitting={submitting} done={progress.done} total={progress.total} />
    </div>
  );
}
