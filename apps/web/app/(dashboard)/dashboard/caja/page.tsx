"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";


// ─── Types ────────────────────────────────────────────────────────────────────
type Register = { id: number; name: string; is_active: boolean; has_open_session: boolean };
type Movement = { id: number; type: "IN" | "OUT"; amount: string; description: string; created_by: string; created_at: string };
type LiveSummary = {
  initial_amount: string;
  cash_sales: string; debit_sales: string; card_sales: string; transfer_sales: string; total_sales: string;
  cash_tips: string; movements_in: string; movements_out: string; expected_cash: string;
};
type Session = {
  id: number; register_id: number; register_name: string; status: "OPEN" | "CLOSED";
  opened_by: string; opened_at: string; initial_amount: string;
  closed_at?: string | null; counted_cash?: string | null;
  expected_cash?: string | null; difference?: string | null; note?: string;
  movements?: Movement[];
  live?: LiveSummary;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmt(v: string | number) {
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? Math.round(n).toLocaleString("es-CL") : "0";
}
function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ─── Btn ──────────────────────────────────────────────────────────────────────
function Btn({ children, onClick, variant = "secondary", disabled, full }: {
  children: React.ReactNode; onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost"; disabled?: boolean; full?: boolean;
}) {
  const vs = {
    primary:   { background: C.accent, color: "#fff", border: `1px solid ${C.accent}` },
    secondary: { background: C.surface, color: C.text, border: `1px solid ${C.borderMd}` },
    danger:    { background: C.redBg, color: C.red, border: `1px solid ${C.redBd}` },
    ghost:     { background: "transparent", color: C.mid, border: "1px solid transparent" },
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

// ─── Row ──────────────────────────────────────────────────────────────────────
function FlowRow({ label, amount, color }: { label: string; amount: string; color?: string }) {
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

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════
export default function CajaPage() {
  const [registers, setRegisters]     = useState<Register[]>([]);
  const [session, setSession]         = useState<Session | null>(null);
  const [loading, setLoading]         = useState(true);
  const [err, setErr]                 = useState<string | null>(null);
  const [busy, setBusy]               = useState(false);
  const [tab, setTab]                 = useState<"live" | "history">("live");
  const [history, setHistory]         = useState<Session[]>([]);
  const [histLoad, setHistLoad]       = useState(false);

  // Open session form
  const [selRegister, setSelRegister] = useState<number | "">("");
  const [initialAmt, setInitialAmt]   = useState("");

  // Close session modal
  const [showClose, setShowClose]     = useState(false);
  const [countedCash, setCountedCash] = useState("");
  const [closeNote, setCloseNote]     = useState("");

  // Add movement modal
  const [showMove, setShowMove]       = useState(false);
  const [moveType, setMoveType]       = useState<"IN" | "OUT">("IN");
  const [moveAmt, setMoveAmt]         = useState("");
  const [moveDesc, setMoveDesc]       = useState("");

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const [regs, sess] = await Promise.allSettled([
        apiFetch("/caja/registers/"),
        apiFetch("/caja/sessions/current/"),
      ]);
      if (regs.status === "fulfilled") setRegisters(regs.value as Register[]);
      if (sess.status === "fulfilled") setSession(sess.value as Session);
      else setSession(null);
    } catch (e: any) { setErr(e?.message ?? "Error cargando caja"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const [histPage, setHistPage] = useState(1);
  const [histTotal, setHistTotal] = useState(0);

  const loadHistory = useCallback(async (page = 1) => {
    setHistLoad(true);
    try {
      const data: any = await apiFetch(`/caja/sessions/history/?page=${page}`);
      // Soportar respuesta paginada (object) y legacy (array)
      if (Array.isArray(data)) {
        setHistory(data as Session[]);
        setHistTotal(data.length);
      } else {
        setHistory((data.results || []) as Session[]);
        setHistTotal(data.count || 0);
        setHistPage(data.page || 1);
      }
    } catch { setHistory([]); setHistTotal(0); }
    finally { setHistLoad(false); }
  }, []);

  useEffect(() => { if (tab === "history") loadHistory(); }, [tab, loadHistory]);

  // Periodic refresh of live session
  useEffect(() => {
    if (!session || session.status !== "OPEN") return;
    const iv = setInterval(() => {
      apiFetch("/caja/sessions/current/").then(s => setSession(s as Session)).catch(() => {});
    }, 30_000);
    return () => clearInterval(iv);
  }, [session?.id, session?.status]);

  const openSession = async () => {
    if (!selRegister) { setErr("Selecciona una caja"); return; }
    setBusy(true); setErr(null);
    try {
      const s = await apiFetch(`/caja/registers/${selRegister}/open/`, {
        method: "POST",
        body: JSON.stringify({ initial_amount: Number(initialAmt) || 0 }),
      });
      setSession(s as Session);
      setSelRegister(""); setInitialAmt("");
      // Refresh registers to update has_open_session
      const regs = await apiFetch("/caja/registers/");
      setRegisters(regs as Register[]);
    } catch (e: any) { setErr(e?.message ?? "Error abriendo arqueo"); }
    finally { setBusy(false); }
  };

  const addMovement = async () => {
    if (!session) return;
    setBusy(true); setErr(null);
    try {
      await apiFetch(`/caja/sessions/${session.id}/movements/`, {
        method: "POST",
        body: JSON.stringify({ type: moveType, amount: Number(moveAmt), description: moveDesc }),
      });
      const s = await apiFetch(`/caja/sessions/${session.id}/`);
      setSession(s as Session);
      setShowMove(false); setMoveAmt(""); setMoveDesc("");
    } catch (e: any) { setErr(e?.message ?? "Error agregando movimiento"); }
    finally { setBusy(false); }
  };

  const closeSession = async () => {
    if (!session) return;
    setBusy(true); setErr(null);
    try {
      await apiFetch(`/caja/sessions/${session.id}/close/`, {
        method: "POST",
        body: JSON.stringify({ counted_cash: Number(countedCash) || 0, note: closeNote }),
      });
      setSession(null); setShowClose(false); setCountedCash(""); setCloseNote("");
      if (tab === "history") loadHistory();
      const regs = await apiFetch("/caja/registers/");
      setRegisters(regs as Register[]);
    } catch (e: any) { setErr(e?.message ?? "Error cerrando arqueo"); }
    finally { setBusy(false); }
  };

  const live = session?.live;
  const difference = showClose && countedCash !== "" && live
    ? Number(countedCash) - Number(live.expected_cash)
    : session?.difference ? Number(session.difference) : null;

  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: "24px 16px", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>

      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: C.text }}>Caja</div>
        <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>Gestión de arqueos y flujo de efectivo</div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: `1px solid ${C.border}`, paddingBottom: 0 }}>
        {(["live", "history"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
            background: "none", border: "none",
            color: tab === t ? C.accent : C.mid,
            borderBottom: tab === t ? `2px solid ${C.accent}` : "2px solid transparent",
            marginBottom: -1,
          }}>
            {t === "live" ? "Arqueo activo" : "Historial"}
          </button>
        ))}
      </div>

      {err && (
        <div style={{ padding: "10px 14px", background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: C.r, fontSize: 13, color: C.red, marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
          {err}
          <button onClick={() => setErr(null)} style={{ background: "none", border: "none", cursor: "pointer", color: C.red }}>✕</button>
        </div>
      )}

      {/* ── LIVE TAB ─────────────────────────────────────────────────────────── */}
      {tab === "live" && (
        loading ? (
          <div style={{ textAlign: "center", padding: 48 }}><Spinner /></div>
        ) : session ? (
          /* Open session view */
          <div style={{ display: "grid", gap: 16 }}>
            {/* Header */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{session.register_name}</div>
                <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
                  Abierto por <b style={{ color: C.text }}>{session.opened_by}</b> · {fmtDate(session.opened_at)}
                </div>
              </div>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 12px", borderRadius: 99, background: C.greenBg, border: `1px solid ${C.greenBd}`, color: C.green, fontSize: 12, fontWeight: 700 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: C.green }} />
                Sesión abierta
              </div>
            </div>

            {/* Sales breakdown by payment method */}
            {live && (
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
                <div style={{ padding: "12px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>
                  Ventas del turno
                </div>
                <div style={{ padding: "8px 20px" }}>
                  {[
                    { label: "Efectivo",       amount: live.cash_sales },
                    { label: "Débito",         amount: live.debit_sales },
                    { label: "Crédito",        amount: live.card_sales },
                    { label: "Transferencia",  amount: live.transfer_sales },
                  ].map(r => (
                    <FlowRow key={r.label} label={r.label} amount={r.amount} color={Number(r.amount) > 0 ? C.green : C.mid} />
                  ))}
                  <div style={{ borderTop: `2px solid ${C.border}`, marginTop: 4, paddingTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 8 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>Total ventas</span>
                    <span style={{ fontSize: 20, fontWeight: 900, color: C.text, fontVariantNumeric: "tabular-nums" }}>${fmt(live.total_sales)}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Cash flow (physical cash only) */}
            {live && (
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
                <div style={{ padding: "12px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>
                  Flujo de caja (efectivo físico)
                </div>
                <div style={{ padding: "8px 20px" }}>
                  <FlowRow label="Fondo inicial" amount={live.initial_amount} color={C.green} />
                  <div style={{ borderTop: `1px solid ${C.border}` }} />
                  <FlowRow label="Ventas en efectivo" amount={live.cash_sales} color={C.green} />
                  <FlowRow label="Propinas en efectivo" amount={live.cash_tips} color={C.green} />
                  <FlowRow label="Ingresos manuales" amount={live.movements_in} color={C.green} />
                  <FlowRow label="Egresos / Retiros" amount={`-${live.movements_out}`} color={Number(live.movements_out) > 0 ? C.red : C.mid} />
                  <div style={{ borderTop: `2px solid ${C.border}`, marginTop: 4, paddingTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 8 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>Efectivo esperado en caja</span>
                    <span style={{ fontSize: 22, fontWeight: 900, color: C.accent, fontVariantNumeric: "tabular-nums" }}>${fmt(live.expected_cash)}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Movements */}
            {session.movements && session.movements.length > 0 && (
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, overflow: "hidden" }}>
                <div style={{ padding: "12px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, fontWeight: 700, fontSize: 13 }}>Movimientos no-venta</div>
                {session.movements.map(m => (
                  <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 20px", borderBottom: `1px solid ${C.border}` }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{m.description}</div>
                      <div style={{ fontSize: 11, color: C.mute }}>{fmtDate(m.created_at)} · {m.created_by}</div>
                    </div>
                    <span style={{ fontSize: 14, fontWeight: 700, color: m.type === "IN" ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                      {m.type === "IN" ? "+" : "-"}${fmt(m.amount)}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: "flex", gap: 10 }}>
              <Btn variant="secondary" onClick={() => setShowMove(true)} disabled={busy}>+ Agregar movimiento</Btn>
              <Btn variant="danger" onClick={() => setShowClose(true)} disabled={busy}>Cerrar arqueo</Btn>
            </div>
          </div>
        ) : (
          /* No open session — show open form */
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "28px 28px", maxWidth: 480 }}>
            <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 4 }}>Abrir nuevo arqueo</div>
            <div style={{ fontSize: 13, color: C.mute, marginBottom: 20 }}>Selecciona la caja e ingresa el fondo inicial en efectivo.</div>

            <div style={{ display: "grid", gap: 14 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Caja</div>
                {registers.length === 0 ? (
                  <div style={{ fontSize: 13, color: C.mute }}>
                    No hay cajas creadas.{" "}
                    <button onClick={async () => {
                      const name = prompt("Nombre de la nueva caja:");
                      if (!name) return;
                      await apiFetch("/caja/registers/", { method: "POST", body: JSON.stringify({ name }) });
                      load();
                    }} style={{ background: "none", border: "none", color: C.accent, cursor: "pointer", fontSize: 13, fontWeight: 600 }}>Crear primera caja</button>
                  </div>
                ) : (
                  <select value={selRegister} onChange={e => setSelRegister(e.target.value ? Number(e.target.value) : "")}
                    style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14 }}>
                    <option value="">-- Selecciona --</option>
                    {registers.map(r => (
                      <option key={r.id} value={r.id} disabled={r.has_open_session}>{r.name}{r.has_open_session ? " (ocupada)" : ""}</option>
                    ))}
                  </select>
                )}
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Fondo inicial (efectivo)</div>
                <input value={initialAmt} onChange={e => setInitialAmt(e.target.value)}
                  placeholder="$0" inputMode="decimal"
                  style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
              </div>
              <Btn variant="primary" onClick={openSession} disabled={busy || !selRegister} full>
                {busy ? <><Spinner size={14} /> Abriendo…</> : "Abrir arqueo"}
              </Btn>
            </div>
          </div>
        )
      )}

      {/* ── HISTORY TAB ──────────────────────────────────────────────────────── */}
      {tab === "history" && (
        histLoad ? (
          <div style={{ textAlign: "center", padding: 48 }}><Spinner /></div>
        ) : history.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: C.mute, fontSize: 14 }}>Sin arqueos cerrados.</div>
        ) : (
          <>
            <div style={{ display: "grid", gap: 10 }}>
              {history.map(s => {
                const diff = Number(s.difference ?? 0);
                return (
                  <div key={s.id} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "14px 18px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>{s.register_name}</div>
                        <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>
                          {fmtDate(s.opened_at)} → {s.closed_at ? fmtDate(s.closed_at) : "—"}
                        </div>
                        <div style={{ fontSize: 12, color: C.mute }}>Cajero: {s.opened_by}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 11, color: C.mute }}>Diferencia</div>
                        <div style={{ fontSize: 16, fontWeight: 800, color: diff >= 0 ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                          {diff >= 0 ? "+" : ""}${fmt(Math.abs(diff))}
                        </div>
                      </div>
                    </div>
                    <div style={{ marginTop: 10, display: "flex", gap: 24, fontSize: 12, color: C.mid }}>
                      <span>Esperado: <b style={{ color: C.text }}>${fmt(s.expected_cash ?? 0)}</b></span>
                      <span>Contado: <b style={{ color: C.text }}>${fmt(s.counted_cash ?? 0)}</b></span>
                    </div>
                  </div>
                );
              })}
            </div>
            {/* Paginación */}
            {histTotal > 20 && (
              <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 12 }}>
                <button
                  disabled={histPage <= 1}
                  onClick={() => { const p = histPage - 1; setHistPage(p); loadHistory(p); }}
                  style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: histPage <= 1 ? "default" : "pointer", opacity: histPage <= 1 ? 0.4 : 1, fontSize: 13 }}
                >← Anterior</button>
                <span style={{ fontSize: 13, color: C.mid, alignSelf: "center" }}>
                  Página {histPage} de {Math.ceil(histTotal / 20)}
                </span>
                <button
                  disabled={histPage >= Math.ceil(histTotal / 20)}
                  onClick={() => { const p = histPage + 1; setHistPage(p); loadHistory(p); }}
                  style={{ padding: "6px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, cursor: histPage >= Math.ceil(histTotal / 20) ? "default" : "pointer", opacity: histPage >= Math.ceil(histTotal / 20) ? 0.4 : 1, fontSize: 13 }}
                >Siguiente →</button>
              </div>
            )}
          </>
        )
      )}

      {/* ── MODAL: AGREGAR MOVIMIENTO ────────────────────────────────────────── */}
      {showMove && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: 400, boxShadow: "0 20px 52px rgba(0,0,0,0.18)" }}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 16 }}>Agregar movimiento</div>
            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Tipo</div>
                <div style={{ display: "flex", gap: 8 }}>
                  {(["IN", "OUT"] as const).map(t => (
                    <button key={t} onClick={() => setMoveType(t)} style={{
                      flex: 1, padding: "8px 0", borderRadius: C.r, fontSize: 13, fontWeight: 600, cursor: "pointer",
                      background: moveType === t ? (t === "IN" ? C.greenBg : C.redBg) : C.bg,
                      border: `1px solid ${moveType === t ? (t === "IN" ? C.greenBd : C.redBd) : C.border}`,
                      color: moveType === t ? (t === "IN" ? C.green : C.red) : C.mid,
                    }}>
                      {t === "IN" ? "↑ Ingreso" : "↓ Egreso"}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Monto</div>
                <input value={moveAmt} onChange={e => setMoveAmt(e.target.value)} placeholder="$0" inputMode="decimal"
                  style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Descripción</div>
                <input value={moveDesc} onChange={e => setMoveDesc(e.target.value)} placeholder="Ej: Compra de gas, Retiro para banco…"
                  style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
              <Btn variant="ghost" onClick={() => setShowMove(false)} disabled={busy}>Cancelar</Btn>
              <Btn variant="primary" onClick={addMovement} disabled={busy || !moveAmt || !moveDesc}>
                {busy ? <Spinner size={14} /> : "Agregar"}
              </Btn>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: CERRAR ARQUEO ─────────────────────────────────────────────── */}
      {showClose && live && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: C.surface, borderRadius: 14, padding: 28, width: 440, boxShadow: "0 20px 52px rgba(0,0,0,0.18)" }}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 6 }}>Cerrar arqueo</div>
            <div style={{ fontSize: 13, color: C.mute, marginBottom: 18 }}>Cuenta el efectivo en caja e ingresa el monto real.</div>
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ padding: "12px 16px", background: C.bg, borderRadius: C.r, display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, color: C.mid }}>Efectivo esperado</span>
                <span style={{ fontSize: 16, fontWeight: 800, color: C.text }}>${fmt(live.expected_cash)}</span>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Efectivo contado en caja</div>
                <input value={countedCash} onChange={e => setCountedCash(e.target.value)} placeholder="$0" inputMode="decimal" autoFocus
                  style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
              </div>
              {countedCash !== "" && (
                <div style={{ padding: "10px 14px", borderRadius: C.r, background: difference !== null && difference >= 0 ? C.greenBg : C.redBg, border: `1px solid ${difference !== null && difference >= 0 ? C.greenBd : C.redBd}` }}>
                  <div style={{ fontSize: 12, color: C.mid }}>Diferencia</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: difference !== null && difference >= 0 ? C.green : C.red, fontVariantNumeric: "tabular-nums" }}>
                    {difference !== null && difference >= 0 ? "+" : ""}${fmt(difference ?? 0)}
                  </div>
                  {difference !== null && difference < 0 && <div style={{ fontSize: 11, color: C.red, marginTop: 2 }}>Hay un faltante de ${fmt(Math.abs(difference))}</div>}
                  {difference !== null && difference > 0 && <div style={{ fontSize: 11, color: C.green, marginTop: 2 }}>Hay un sobrante de ${fmt(difference)}</div>}
                </div>
              )}
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Nota (opcional)</div>
                <input value={closeNote} onChange={e => setCloseNote(e.target.value)} placeholder="Ej: Todo en orden"
                  style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
              <Btn variant="ghost" onClick={() => setShowClose(false)} disabled={busy}>Cancelar</Btn>
              <Btn variant="danger" onClick={closeSession} disabled={busy || countedCash === ""}>
                {busy ? <Spinner size={14} /> : "Confirmar cierre"}
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
