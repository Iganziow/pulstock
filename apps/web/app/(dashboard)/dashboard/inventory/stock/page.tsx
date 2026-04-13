"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { Spinner, SkeletonPage } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
import {
  Btn, StockBadge, OkBanner, toNum, fQty, sanitizePos,
  type Warehouse, type StockRow,
} from "@/components/inventory/StockShared";
import { ReceiveModal, IssueModal, AdjustModal, TransferModal } from "@/components/inventory/StockModals";

export default function StockPage() {
  useGlobalStyles();
  const mob = useIsMobile();
  const router = useRouter();

  const [meErr, setMeErr] = useState<string | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId, setWarehouseId] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [items, setItems] = useState<StockRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const activeWh = useMemo(() => warehouses.filter(w => w.is_active), [warehouses]);
  const whName = useMemo(() => activeWh.find(w => w.id === warehouseId)?.name ?? `#${warehouseId}`, [activeWh, warehouseId]);

  // ── selected row for modals ───────────────────────────────────────────────
  const [sel, setSel] = useState<StockRow | null>(null);

  // ── ADJUST state ──────────────────────────────────────────────────────────
  const [adjOpen, setAdjOpen] = useState(false);
  const [adjQty, setAdjQty] = useState("");
  const [adjCost, setAdjCost] = useState("");
  const [adjNote, setAdjNote] = useState("Ajuste manual");
  const [adjBusy, setAdjBusy] = useState(false);
  const [adjErr, setAdjErr] = useState<string | null>(null);

  // ── RECEIVE state ─────────────────────────────────────────────────────────
  const [recOpen, setRecOpen] = useState(false);
  const [recQty, setRecQty] = useState("");
  const [recCost, setRecCost] = useState("");
  const [recNote, setRecNote] = useState("Recepcion");
  const [recBusy, setRecBusy] = useState(false);
  const [recErr, setRecErr] = useState<string | null>(null);

  // ── ISSUE state ───────────────────────────────────────────────────────────
  const [issOpen, setIssOpen] = useState(false);
  const [issQty, setIssQty] = useState("");
  const [issReason, setIssReason] = useState<string>("MERMA");
  const [issNote, setIssNote] = useState("Salida");
  const [issBusy, setIssBusy] = useState(false);
  const [issErr, setIssErr] = useState<string | null>(null);

  // ── TRANSFER state ────────────────────────────────────────────────────────
  const [trOpen, setTrOpen] = useState(false);
  const [trProdId, setTrProdId] = useState<number | null>(null);
  const [trTarget, setTrTarget] = useState<number | null>(null);
  const [trQty, setTrQty] = useState("");
  const [trNote, setTrNote] = useState("Transferencia");
  const [trBusy, setTrBusy] = useState(false);
  const [trErr, setTrErr] = useState<string | null>(null);

  const anyBusy = adjBusy || recBusy || issBusy || trBusy;

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key !== "Escape" || anyBusy) return; setAdjOpen(false); setRecOpen(false); setIssOpen(false); setTrOpen(false); }
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  }, [anyBusy]);

  useEffect(() => { setAdjOpen(false); setRecOpen(false); setIssOpen(false); setTrOpen(false); setSel(null); }, [warehouseId]);

  // boot
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const me = (await apiFetch("/core/me/")) as Me;
        if (!me?.tenant_id) { setMeErr("Tu usuario no tiene tenant asignado."); return; }
        const whs = (await apiFetch("/core/warehouses/")) as Warehouse[];
        const list = Array.isArray(whs) ? whs : [];
        setWarehouses(list);
        const active = list.filter(w => w.is_active);
        if (!active.length) { setMeErr("No tienes bodegas activas."); return; }
        const preferred = me.default_warehouse_id && active.some(w => w.id === me.default_warehouse_id) ? me.default_warehouse_id : active[0].id;
        setMeErr(null); setWarehouseId(preferred);
      } catch (e: any) { setMeErr(e?.message ?? "No se pudo cargar configuracion."); }
      finally { setLoading(false); }
    })();
  }, []);

  const endpoint = useMemo(() => {
    if (!warehouseId) return null;
    const qq = q.trim(); const params = new URLSearchParams();
    params.set("warehouse_id", String(warehouseId)); params.set("page", String(page));
    if (qq) params.set("q", qq);
    return `/inventory/stock/?${params.toString()}`;
  }, [warehouseId, q, page]);

  useEffect(() => { setPage(1); }, [q, warehouseId]);

  async function load() {
    if (!endpoint) return;
    setLoading(true); setErr(null);
    try { const data = await apiFetch(endpoint); setItems(data?.results ?? []); setTotalCount(data?.count ?? data?.results?.length ?? 0); }
    catch (e: any) { setErr(e?.message ?? "Error cargando stock"); setItems([]); setTotalCount(0); }
    finally { setLoading(false); }
  }

  useEffect(() => { if (!endpoint) return; const t = setTimeout(() => load(), 250); return () => clearTimeout(t); }, [endpoint]); // eslint-disable-line

  function showOk(msg: string) { setOkMsg(msg); setTimeout(() => setOkMsg(null), 3500); }

  function openAdj(r: StockRow) { setSel(r); setAdjQty(""); setAdjCost(""); setAdjNote("Ajuste manual"); setAdjErr(null); setAdjOpen(true); }
  function openRec(r: StockRow) { setSel(r); setRecQty(""); setRecCost(""); setRecNote("Recepcion"); setRecErr(null); setRecOpen(true); }
  function openIss(r: StockRow) { setSel(r); setIssQty(""); setIssReason("MERMA"); setIssNote("Salida"); setIssErr(null); setIssOpen(true); }
  function openTr() {
    setSel(null); setTrProdId(null); setTrQty(""); setTrNote("Transferencia"); setTrErr(null);
    const other = activeWh.find(w => w.id !== warehouseId) ?? null;
    setTrTarget(other?.id ?? null); setTrOpen(true);
  }

  // ── submit handlers ───────────────────────────────────────────────────────
  async function submitAdj() {
    if (!sel || !warehouseId) return;
    const adjDelta = toNum(adjQty); const adjCostN = adjCost.trim() ? toNum(adjCost) : null;
    setAdjBusy(true); setAdjErr(null);
    try {
      const body: Record<string, unknown> = { warehouse_id: warehouseId, product_id: sel.product_id, qty: adjDelta, note: adjNote };
      if (adjCostN !== null && !isNaN(adjCostN) && adjCostN >= 0) body.new_avg_cost = adjCostN;
      await apiFetch("/inventory/adjust/", { method: "POST", body: JSON.stringify(body) });
      await load(); setAdjOpen(false); showOk(`Ajuste aplicado en ${sel.name}`);
    } catch (e: any) { setAdjErr(e?.message ?? "No se pudo ajustar."); }
    finally { setAdjBusy(false); }
  }

  async function submitRec() {
    if (!sel || !warehouseId) return;
    const recQtyN = toNum(recQty); const recCostN = recCost.trim() ? toNum(recCost) : 0;
    setRecBusy(true); setRecErr(null);
    try {
      await apiFetch("/inventory/receive/", { method: "POST", body: JSON.stringify({ warehouse_id: warehouseId, product_id: sel.product_id, qty: String(recQtyN), unit_cost: recCost.trim() ? String(recCostN) : null, note: recNote }) });
      await load(); setRecOpen(false); showOk(`Recepcion de ${recQtyN} x ${sel.name}`);
    } catch (e: any) { setRecErr(e?.message ?? "No se pudo recibir."); }
    finally { setRecBusy(false); }
  }

  async function submitIss() {
    if (!sel || !warehouseId) return;
    const issQtyN = toNum(issQty);
    setIssBusy(true); setIssErr(null);
    try {
      await apiFetch("/inventory/issue/", { method: "POST", body: JSON.stringify({ warehouse_id: warehouseId, product_id: sel.product_id, qty: String(issQtyN), reason: issReason, note: issNote }) });
      await load(); setIssOpen(false); showOk(`Salida de ${issQtyN} x ${sel.name}`);
    } catch (e: any) { setIssErr(e?.message ?? "No se pudo egresar."); }
    finally { setIssBusy(false); }
  }

  async function submitTr() {
    if (!warehouseId || !trTarget || !trProdId) return;
    const trQtyN = toNum(trQty);
    setTrBusy(true); setTrErr(null);
    try {
      const resp = await apiFetch("/inventory/transfer/", { method: "POST", body: JSON.stringify({ from_warehouse_id: warehouseId, to_warehouse_id: trTarget, lines: [{ product_id: trProdId, qty: String(trQtyN), note: trNote }] }) }) as any;
      setTrOpen(false);
      const tid = resp?.transfer_id ?? resp?.id ?? null;
      if (tid) { router.push(`/dashboard/inventory/transfers/${tid}`); return; }
      await load();
    } catch (e: any) { setTrErr(e?.message ?? "No se pudo transferir."); }
    finally { setTrBusy(false); }
  }

  const metrics = useMemo(() => {
    const total = items.length;
    const low = items.filter(r => { const n = toNum(r.on_hand); return !isNaN(n) && n > 0 && n <= 5; }).length;
    const zero = items.filter(r => toNum(r.on_hand) <= 0).length;
    const totalUnits = items.reduce((a, r) => { const n = toNum(r.on_hand); return a + (isNaN(n) ? 0 : n); }, 0);
    return { total, low, zero, totalUnits };
  }, [items]);

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "16px 12px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* HEADER */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <div style={{ width: 4, height: 26, background: C.accent, borderRadius: 2 }} />
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: "-0.04em" }}>Stock actual</h1>
            <span style={{ fontSize: 12, color: C.mute, fontWeight: 500, padding: "2px 8px", borderRadius: 99, border: `1px solid ${C.border}`, background: C.surface }}>{whName}</span>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: C.mute, paddingLeft: 14 }}>Stock teorico (on_hand) por bodega</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Btn variant="danger" size="sm" onClick={() => router.push("/dashboard/inventory/salidas")} disabled={!!meErr || !warehouseId}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12l7 7 7-7" /></svg>
            Salida masiva
          </Btn>
          {activeWh.length >= 2 && (
            <Btn variant="sky" size="sm" onClick={openTr} disabled={!!meErr || !warehouseId || loading}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
              Transferir
            </Btn>
          )}
          <Btn variant="secondary" size="sm" onClick={load} disabled={loading || !!meErr || !warehouseId}>
            {loading ? <Spinner /> : <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" /></svg>}
            Recargar
          </Btn>
        </div>
      </div>

      {okMsg && <OkBanner msg={okMsg} />}
      {meErr && <div style={{ padding: "11px 14px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13, fontWeight: 600 }}>{meErr}</div>}

      {/* STAT CARDS */}
      {!meErr && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 10 }}>
          {[
            { label: "Productos", value: String(metrics.total), color: C.accent, sub: "en bodega" },
            { label: "Unidades tot.", value: metrics.totalUnits.toLocaleString("es-CL", { maximumFractionDigits: 0 }), color: C.accent, sub: "on_hand total" },
            { label: "Stock bajo", value: String(metrics.low), color: C.amber, sub: "≤ 5 unidades" },
            { label: "Sin stock", value: String(metrics.zero), color: C.red, sub: "on_hand = 0" },
          ].map(s => (
            <div key={s.label} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "12px 16px", boxShadow: C.sh }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6 }}>{s.label}</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: s.color, letterSpacing: "-0.03em", fontVariantNumeric: "tabular-nums" }}>{s.value}</div>
              <div style={{ fontSize: 11, color: C.mute, marginTop: 3 }}>{s.sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* FILTERS */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        {activeWh.length > 1 && (
          <select value={warehouseId ?? ""} onChange={e => setWarehouseId(Number(e.target.value))} disabled={!!meErr || loading}
            style={{ height: 36, padding: "0 10px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, background: C.surface, minWidth: 160 }}>
            {activeWh.map(w => <option key={w.id} value={w.id}>{w.name}{w.warehouse_type === "sales_floor" ? " (Sala)" : " (Bodega)"}</option>)}
          </select>
        )}
        <div style={{ position: "relative", flex: 1, minWidth: 220, maxWidth: 440 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
            style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar por nombre o SKU..."
            style={{ width: "100%", height: 36, padding: "0 10px 0 34px", border: `1px solid ${C.border}`, borderRadius: C.r, fontSize: 13, background: C.surface }}
            disabled={!!meErr || !warehouseId} />
        </div>
      </div>

      {/* TABLE */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden", boxShadow: C.sh }}>
        <div style={{ overflowX: "auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: mob?"1fr 80px 140px":"1fr 100px 110px 130px 100px 110px 200px", columnGap: mob?6:12, padding: mob?"10px 10px":"10px 18px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontSize: 10.5, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.08em", minWidth: mob ? 340 : undefined }}>
            <div>Producto</div>{!mob&&<div>SKU</div>}{!mob&&<div>Categoria</div>}{!mob&&<div>Barcode</div>}
            <div style={{ textAlign: "right" }}>Stock</div>
            {!mob&&<div style={{ textAlign: "right" }}>Costo prom.</div>}
            <div style={{ textAlign: "right" }}>Acciones</div>
          </div>

          {loading && <SkeletonPage cards={0} rows={8} />}
          {err && <div style={{ padding: "18px" }}><div style={{ padding: "10px 12px", borderRadius: C.r, border: `1px solid ${C.redBd}`, background: C.redBg, color: C.red, fontSize: 13 }}>{err}</div></div>}
          {!loading && !err && items.length === 0 && !meErr && (
            <div style={{ padding: "52px 24px", textAlign: "center" }}>
              <div style={{ fontSize: 36, marginBottom: 10 }}>📦</div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>Sin stock registrado</div>
              <div style={{ fontSize: 13, color: C.mute }}>Usa &quot;Recibir&quot; en cualquier producto para cargar inventario inicial</div>
            </div>
          )}

          {!loading && !err && items.map((r, i) => {
            const n = toNum(r.on_hand);
            const isLow = !isNaN(n) && n > 0 && n <= 5;
            const isZero = !isNaN(n) && n <= 0;
            return (
              <div key={r.product_id} className="prow" style={{ display: "grid", gridTemplateColumns: mob?"1fr 80px 140px":"1fr 100px 110px 130px 100px 110px 200px", columnGap: mob?6:12, padding: mob?"11px 10px":"11px 18px", borderBottom: i < items.length - 1 ? `1px solid ${C.border}` : "none", alignItems: "center", borderLeft: isZero ? `3px solid ${C.red}` : isLow ? `3px solid ${C.amber}` : "3px solid transparent", minWidth: mob ? 340 : undefined }}>
                <div style={{minWidth:0}}>
                  <div style={{ fontWeight: 600, fontSize: mob?12:13, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.name}</div>
                  {mob&&<div style={{fontSize:10,color:C.mute,fontFamily:C.mono,marginTop:1}}>{r.sku??""}</div>}
                  {(isZero || isLow) && <div style={{ fontSize: 10, color: isZero ? C.red : C.amber, fontWeight: 700, marginTop: 2 }}>{isZero ? "Sin stock" : "Stock bajo"}</div>}
                </div>
                {!mob&&<div style={{ fontSize: 12, color: C.mid, fontFamily: C.mono }}>{r.sku ?? "-"}</div>}
                {!mob&&<div style={{ fontSize: 12, color: C.mid }}>{r.category ?? "-"}</div>}
                {!mob&&<div style={{ fontSize: 11, color: C.mute, fontFamily: C.mono }}>{r.barcode ?? "-"}</div>}
                <div style={{ textAlign: "right" }}><StockBadge val={r.on_hand} /></div>
                {!mob&&<div style={{ textAlign: "right", fontSize: 12, color: C.mid, fontFamily: "monospace" }}>
                  {r.avg_cost && toNum(r.avg_cost) > 0 ? `$${Math.round(toNum(r.avg_cost)).toLocaleString("es-CL")}` : "-"}
                </div>}
                <div style={{ display: "flex", justifyContent: "flex-end", gap: mob?3:5, flexWrap:mob?"wrap":"nowrap" }}>
                  <Btn variant="success" size="sm" onClick={() => openRec(r)} disabled={!!meErr || !warehouseId}>{mob?"+":"Recibir"}</Btn>
                  <Btn variant="danger" size="sm" onClick={() => openIss(r)} disabled={!!meErr || !warehouseId}>{mob?"−":"Egresar"}</Btn>
                  <Btn variant="secondary" size="sm" onClick={() => openAdj(r)} disabled={!!meErr || !warehouseId}>{mob?"⇄":"Ajustar"}</Btn>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* PAGINATION */}
      {!loading && items.length > 0 && (() => {
        const PAGE_SIZE = 50;
        const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
        return <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 4px", flexWrap: "wrap", gap: 8 }}>
          <div style={{ fontSize: 12, color: C.mute }}>{totalCount} producto{totalCount !== 1 ? "s" : ""} · Bodega: {whName}</div>
          {totalPages > 1 && <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Btn variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>← Anterior</Btn>
            <span style={{ fontSize: 12, color: C.mid }}>Pag <b style={{ color: C.text }}>{page}</b> de <b style={{ color: C.text }}>{totalPages}</b></span>
            <Btn variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Siguiente →</Btn>
          </div>}
        </div>;
      })()}

      {/* MODALS */}
      {recOpen && sel && <ReceiveModal sel={sel} whName={whName} recQty={recQty} setRecQty={setRecQty} recCost={recCost} setRecCost={setRecCost} recNote={recNote} setRecNote={setRecNote} recBusy={recBusy} recErr={recErr} setRecErr={setRecErr} onClose={() => setRecOpen(false)} onSubmit={submitRec} />}
      {issOpen && sel && <IssueModal sel={sel} whName={whName} issQty={issQty} setIssQty={setIssQty} issReason={issReason} setIssReason={setIssReason} issNote={issNote} setIssNote={setIssNote} issBusy={issBusy} issErr={issErr} setIssErr={setIssErr} onClose={() => setIssOpen(false)} onSubmit={submitIss} />}
      {adjOpen && sel && <AdjustModal sel={sel} whName={whName} adjQty={adjQty} setAdjQty={setAdjQty} adjCost={adjCost} setAdjCost={setAdjCost} adjNote={adjNote} setAdjNote={setAdjNote} adjBusy={adjBusy} adjErr={adjErr} setAdjErr={setAdjErr} onClose={() => setAdjOpen(false)} onSubmit={submitAdj} />}
      {trOpen && <TransferModal whName={whName} warehouseId={warehouseId} activeWh={activeWh} items={items} trTarget={trTarget} setTrTarget={setTrTarget} trProdId={trProdId} setTrProdId={setTrProdId} trQty={trQty} setTrQty={setTrQty} trNote={trNote} setTrNote={setTrNote} trBusy={trBusy} trErr={trErr} setTrErr={setTrErr} onClose={() => setTrOpen(false)} onSubmit={submitTr} />}
    </div>
  );
}
