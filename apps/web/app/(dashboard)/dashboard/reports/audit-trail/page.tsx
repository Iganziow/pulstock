"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";
import { humanizeError } from "@/lib/errors";



const fmt = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL"); };
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (d: number) => { const t = new Date(); t.setDate(t.getDate() - d); return t.toISOString().slice(0, 10); };

const REF_LABELS: Record<string, string> = {
  SALE: "Venta", SALE_VOID: "Anulación venta", PURCHASE: "Compra",
  TRANSFER: "Transferencia", ISSUE: "Merma/Egreso", ADJUST: "Ajuste",
  RECEIVE: "Recepción", INIT: "Carga inicial",
};
const MOVE_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  IN: { label: "Entrada", color: C.green, icon: "↓" },
  OUT: { label: "Salida", color: C.red, icon: "↑" },
  ADJ: { label: "Ajuste", color: C.amber, icon: "↔" },
};

type Row = { id: number; created_at: string; product_id: number; product_name: string | null; category: string | null; warehouse_name: string | null; move_type: string; ref_type: string; ref_id: number | null; qty: string; cost_snapshot: string; value_delta: string; reason: string; note: string; user: string | null };
type Summary = { move_count: number; total_in_qty: string; total_out_qty: string; total_value_in: string; total_value_out: string; net_value: string };
type ByType = { ref_type: string; count: number; qty: string };
type ByUser = { user: string; count: number };

export default function AuditTrailPage() {
  const mob = useIsMobile();
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<Row[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [byType, setByType] = useState<ByType[]>([]);
  const [byUser, setByUser] = useState<ByUser[]>([]);
  const [refTypes, setRefTypes] = useState<string[]>([]);
  const [meta, setMeta] = useState<{ page: number; total_pages: number; total: number }>({ page: 1, total_pages: 0, total: 0 });

  const [dateFrom, setDateFrom] = useState(daysAgo(7));
  const [dateTo, setDateTo] = useState(today());
  const [refType, setRefType] = useState("");
  const [moveType, setMoveType] = useState("");
  const [page, setPage] = useState(1);
  const [err, setErr] = useState("");

  const load = async (p = 1) => {
    setLoading(true);
    try {
      setErr("");
      const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, page: String(p), page_size: "50" });
      if (refType) params.set("ref_type", refType);
      if (moveType) params.set("move_type", moveType);
      const data = await apiFetch(`/reports/audit-trail/?${params}`);
      setRows(data?.results || []);
      setSummary(data?.summary || null);
      setByType(data?.by_type || []);
      setByUser(data?.by_user || []);
      setRefTypes(data?.ref_types || []);
      setMeta({ page: data?.meta?.page || p, total_pages: data?.meta?.total_pages || 0, total: data?.meta?.total || 0 });
    } catch (e: any) { setErr(humanizeError(e, "Error al cargar el reporte")); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const iS: React.CSSProperties = { padding: "7px 10px", border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 13, fontFamily: C.font, background: C.surface, outline: "none" };
  const maxTypeCount = Math.max(...byType.map(t => t.count), 1);

  return (
    <div style={{ fontFamily: C.font, color: C.text, background: C.bg, minHeight: "100vh", padding: mob ? "14px 10px" : "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <Link href="/dashboard/reports" style={{ fontSize: 12, color: C.mute, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg> Reportes
        </Link>
        <h1 style={{ margin: 0, fontSize: mob ? 19 : 23, fontWeight: 800, letterSpacing: "-.04em" }}>🔒 Auditoría de movimientos</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: C.mute }}>Bitácora completa: quién movió qué, cuándo y por qué</p>
      </div>

      {err && <div style={{margin:"0 0 16px",padding:"10px 16px",borderRadius:8,background:C.redBg,border:`1px solid ${C.redBd}`,color:C.red,fontSize:13,fontWeight:500}}>{err}</div>}

      {/* Filters */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={iS} />
        <span style={{ fontSize: 12, color: C.mute }}>a</span>
        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={iS} />
        <select value={refType} onChange={e => setRefType(e.target.value)} style={{ ...iS, cursor: "pointer", color: refType ? C.text : C.mute }}>
          <option value="">Todos los tipos</option>
          {refTypes.map(t => <option key={t} value={t}>{REF_LABELS[t] || t}</option>)}
        </select>
        <select value={moveType} onChange={e => setMoveType(e.target.value)} style={{ ...iS, cursor: "pointer", color: moveType ? C.text : C.mute }}>
          <option value="">Entrada/Salida</option>
          <option value="IN">Entradas</option>
          <option value="OUT">Salidas</option>
          <option value="ADJ">Ajustes</option>
        </select>
        <button onClick={() => { setPage(1); load(1); }} style={{ ...iS, background: C.accent, color: "#fff", border: "none", cursor: "pointer", fontWeight: 600, padding: "7px 14px" }}>Consultar</button>
      </div>

      {loading && <div style={{ padding: 40, textAlign: "center", color: C.mute }}><Spinner /> Cargando…</div>}

      {/* Summary */}
      {summary && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr 1fr" : "repeat(4, 1fr)", gap: 10 }}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Movimientos</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4 }}>{summary.move_count.toLocaleString("es-CL")}</div>
          </div>
          <div style={{ background: C.greenBg, border: `1px solid #A7F3D0`, borderRadius: C.r, padding: "12px 14px" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.green, textTransform: "uppercase" }}>Entradas</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: C.green, marginTop: 4 }}>{fmt(summary.total_in_qty)} uds</div>
            <div style={{ fontSize: 11, color: C.mid }}>{fmtMoney(summary.total_value_in)}</div>
          </div>
          <div style={{ background: C.redBg, border: `1px solid #FECACA`, borderRadius: C.r, padding: "12px 14px" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.red, textTransform: "uppercase" }}>Salidas</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: C.red, marginTop: 4 }}>{fmt(summary.total_out_qty)} uds</div>
            <div style={{ fontSize: 11, color: C.mid }}>{fmtMoney(summary.total_value_out)}</div>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "12px 14px", boxShadow: C.sh, gridColumn: mob ? "1 / -1" : "auto" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.mute, textTransform: "uppercase" }}>Balance neto</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4, color: parseFloat(summary.net_value) >= 0 ? C.green : C.red }}>{fmtMoney(summary.net_value)}</div>
          </div>
        </div>
      )}

      {/* By type breakdown */}
      {byType.length > 0 && !loading && (
        <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "2fr 1fr", gap: 12 }}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: mob ? "12px" : "14px 16px", boxShadow: C.sh }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8 }}>Por tipo de operación</div>
            {byType.map((t, i) => (
              <div key={i} style={{ marginBottom: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
                  <span style={{ fontWeight: 600 }}>{REF_LABELS[t.ref_type] || t.ref_type}</span>
                  <span style={{ color: C.mid }}>{t.count} mov.</span>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: "#E4E4E7", overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${(t.count / maxTypeCount) * 100}%`, background: C.accent, borderRadius: 2 }} />
                </div>
              </div>
            ))}
          </div>
          {byUser.length > 0 && (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: mob ? "12px" : "14px 16px", boxShadow: C.sh }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 8 }}>Por usuario</div>
              {byUser.map((u, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "4px 0", borderBottom: i < byUser.length - 1 ? `1px solid ${C.border}` : "none" }}>
                  <span style={{ fontWeight: 600 }}>{u.user}</span>
                  <span style={{ color: C.mid }}>{u.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Movement list */}
      {rows.length > 0 && !loading && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, color: C.mute }}>{meta.total} movimientos · Página {meta.page} de {meta.total_pages}</span>
          </div>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, overflow: "hidden", boxShadow: C.sh }}>
            {rows.map((r, i) => {
              const ml = MOVE_LABELS[r.move_type] || { label: r.move_type, color: C.mute, icon: "?" };
              const valDelta = parseFloat(r.value_delta);

              return (
                <div key={r.id} style={{ padding: mob ? "10px 12px" : "8px 16px", borderBottom: i < rows.length - 1 ? `1px solid ${C.border}` : "none", borderLeft: `3px solid ${ml.color}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, flexWrap: "wrap" }}>
                    <div style={{ flex: 1, minWidth: 180 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: ml.color, background: ml.color + "14", padding: "1px 6px", borderRadius: 4 }}>{ml.icon} {ml.label}</span>
                        <span style={{ fontSize: 11, fontWeight: 600, color: C.mid, background: "#F4F4F5", padding: "1px 6px", borderRadius: 4 }}>{REF_LABELS[r.ref_type] || r.ref_type || "—"}</span>
                      </div>
                      <div style={{ fontWeight: 600, fontSize: 13, marginTop: 3 }}>{r.product_name || "—"}</div>
                      {!mob && <div style={{ fontSize: 10, color: C.mute }}>{r.category || ""}{r.warehouse_name && ` · ${r.warehouse_name}`}</div>}
                    </div>
                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                      <div style={{ fontSize: 15, fontWeight: 800, color: ml.color, fontVariantNumeric: "tabular-nums" }}>
                        {r.move_type === "OUT" ? "-" : r.move_type === "IN" ? "+" : ""}{fmt(r.qty)}
                      </div>
                      {valDelta !== 0 && <div style={{ fontSize: 11, color: C.mute }}>{fmtMoney(Math.abs(valDelta))}</div>}
                    </div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.mute, marginTop: 4, flexWrap: "wrap", gap: 4 }}>
                    <span>{new Date(r.created_at).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                    <div style={{ display: "flex", gap: 8 }}>
                      {r.user && <span>👤 {r.user}</span>}
                      {r.reason && <span>📌 {r.reason}</span>}
                      {r.note && <span>📝 {r.note}</span>}
                      {r.ref_id && <span>#{r.ref_id}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {meta.total_pages > 1 && (
            <div style={{ display: "flex", justifyContent: "center", gap: 6 }}>
              <button disabled={meta.page <= 1} onClick={() => { setPage(meta.page - 1); load(meta.page - 1); }} style={{ ...iS, width: 36, padding: "6px", textAlign: "center", cursor: meta.page <= 1 ? "default" : "pointer", opacity: meta.page <= 1 ? .4 : 1 }}>‹</button>
              <span style={{ fontSize: 13, color: C.mid, padding: "6px 12px" }}>{meta.page} / {meta.total_pages}</span>
              <button disabled={meta.page >= meta.total_pages} onClick={() => { setPage(meta.page + 1); load(meta.page + 1); }} style={{ ...iS, width: 36, padding: "6px", textAlign: "center", cursor: meta.page >= meta.total_pages ? "default" : "pointer", opacity: meta.page >= meta.total_pages ? .4 : 1 }}>›</button>
            </div>
          )}
        </>
      )}

      {!loading && rows.length === 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.r, padding: "48px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>🔒</div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Sin movimientos</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 4 }}>No hay movimientos de inventario en este período con los filtros seleccionados.</div>
        </div>
      )}

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}