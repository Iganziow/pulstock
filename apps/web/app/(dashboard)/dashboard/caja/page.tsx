"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Btn, type Register, type Session } from "@/components/caja/CajaShared";
import { CajaLiveSession } from "@/components/caja/CajaLiveSession";
import { CajaHistory } from "@/components/caja/CajaHistory";
import { AddMovementModal, CloseSessionModal } from "@/components/caja/CajaModals";

export default function CajaPage() {
  const mob = useIsMobile();
  const [registers, setRegisters] = useState<Register[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"live" | "history">("live");
  const [history, setHistory] = useState<Session[]>([]);
  const [histLoad, setHistLoad] = useState(false);

  // Open session form
  const [selRegister, setSelRegister] = useState<number | "">("");
  const [initialAmt, setInitialAmt] = useState("");

  // Close session modal
  const [showClose, setShowClose] = useState(false);
  const [countedCash, setCountedCash] = useState("");
  const [closeNote, setCloseNote] = useState("");

  // Add movement modal
  const [showMove, setShowMove] = useState(false);
  const [moveType, setMoveType] = useState<"IN" | "OUT">("IN");
  const [moveAmt, setMoveAmt] = useState("");
  const [moveDesc, setMoveDesc] = useState("");

  // New register modal
  const [showNewRegister, setShowNewRegister] = useState(false);
  const [newRegName, setNewRegName] = useState("");
  const [newRegBusy, setNewRegBusy] = useState(false);
  const [newRegErr, setNewRegErr] = useState("");

  // Timestamp del último refresh exitoso. Mario pidió revisar el flujo
  // de cajas — sin esto el cajero no sabía si los números eran "ahora"
  // o de hace 30s. Útil sobre todo en mañanas con muchas ventas seguidas.
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const [regs, sess] = await Promise.allSettled([apiFetch("/caja/registers/"), apiFetch("/caja/sessions/current/")]);
      if (regs.status === "fulfilled") setRegisters(regs.value as Register[]);
      if (sess.status === "fulfilled") setSession(sess.value as Session);
      else setSession(null);
      setLastUpdated(new Date());
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
      if (Array.isArray(data)) { setHistory(data as Session[]); setHistTotal(data.length); }
      else { setHistory((data.results || []) as Session[]); setHistTotal(data.count || 0); setHistPage(data.page || 1); }
    } catch { setHistory([]); setHistTotal(0); }
    finally { setHistLoad(false); }
  }, []);

  useEffect(() => { if (tab === "history") loadHistory(); }, [tab, loadHistory]);

  // Periodic refresh — actualiza el timestamp para que el usuario sepa
  // que los números están al día.
  useEffect(() => {
    if (!session || session.status !== "OPEN") return;
    const iv = setInterval(() => {
      apiFetch("/caja/sessions/current/")
        .then(s => { setSession(s as Session); setLastUpdated(new Date()); })
        .catch(() => {});
    }, 30_000);
    return () => clearInterval(iv);
  }, [session?.id, session?.status]);

  const openSession = async () => {
    if (!selRegister) { setErr("Selecciona una caja"); return; }
    setBusy(true); setErr(null);
    try {
      const s = await apiFetch(`/caja/registers/${selRegister}/open/`, { method: "POST", body: JSON.stringify({ initial_amount: Number(initialAmt) || 0 }) });
      setSession(s as Session); setSelRegister(""); setInitialAmt("");
      const regs = await apiFetch("/caja/registers/"); setRegisters(regs as Register[]);
    } catch (e: any) { setErr(e?.message ?? "Error abriendo arqueo"); }
    finally { setBusy(false); }
  };

  const addMovement = async () => {
    if (!session) return;
    setBusy(true); setErr(null);
    try {
      await apiFetch(`/caja/sessions/${session.id}/movements/`, { method: "POST", body: JSON.stringify({ type: moveType, amount: Number(moveAmt), description: moveDesc }) });
      const s = await apiFetch(`/caja/sessions/${session.id}/`); setSession(s as Session);
      setShowMove(false); setMoveAmt(""); setMoveDesc("");
    } catch (e: any) { setErr(e?.message ?? "Error agregando movimiento"); }
    finally { setBusy(false); }
  };

  const closeSession = async () => {
    if (!session) return;
    setBusy(true); setErr(null);
    try {
      await apiFetch(`/caja/sessions/${session.id}/close/`, { method: "POST", body: JSON.stringify({ counted_cash: Number(countedCash) || 0, note: closeNote }) });
      setSession(null); setShowClose(false); setCountedCash(""); setCloseNote("");
      if (tab === "history") loadHistory();
      const regs = await apiFetch("/caja/registers/"); setRegisters(regs as Register[]);
    } catch (e: any) { setErr(e?.message ?? "Error cerrando arqueo"); }
    finally { setBusy(false); }
  };

  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: mob ? "16px 12px" : "24px 16px", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>

      <div style={{ marginBottom: 24, display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, color: C.text }}>Caja</div>
          <div style={{ fontSize: 13, color: C.mute, marginTop: 2 }}>Gestion de arqueos y flujo de efectivo</div>
        </div>
        {/* Timestamp + refresh manual. Auto-refresh cada 30s, pero el
            cajero a veces necesita "ver el monto AHORA" (ej: justo
            después de una venta). */}
        {tab === "live" && session && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {lastUpdated && (
              <span style={{ fontSize: 11, color: C.mute, fontVariantNumeric: "tabular-nums" }}>
                Actualizado: <b style={{ color: C.text }}>
                  {lastUpdated.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </b>
              </span>
            )}
            <button
              type="button"
              onClick={() => load()}
              disabled={loading}
              aria-label="Actualizar"
              title="Actualizar ahora"
              style={{
                width: 32, height: 32, borderRadius: C.r,
                border: `1px solid ${C.border}`, background: C.surface,
                color: C.accent, cursor: loading ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                opacity: loading ? 0.6 : 1,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                style={{ animation: loading ? "spin 0.8s linear infinite" : undefined }}>
                <polyline points="23 4 23 10 17 10"/>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
            </button>
          </div>
        )}
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

      {/* LIVE TAB */}
      {tab === "live" && (
        loading ? (
          <div style={{ textAlign: "center", padding: 48 }}><Spinner /></div>
        ) : session ? (
          <CajaLiveSession session={session} busy={busy} onShowMove={() => setShowMove(true)} onShowClose={() => setShowClose(true)} />
        ) : (
          /* No open session -- open form */
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: mob ? "18px 16px" : "28px 28px", maxWidth: 480 }}>
            <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 4 }}>Abrir nuevo arqueo</div>
            <div style={{ fontSize: 13, color: C.mute, marginBottom: 20 }}>Selecciona la caja e ingresa el fondo inicial en efectivo.</div>
            <div style={{ display: "grid", gap: 14 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Caja</div>
                {registers.length === 0 ? (
                  <div style={{ fontSize: 13, color: C.mute }}>
                    No hay cajas creadas.{" "}
                    <button onClick={() => { setNewRegName(""); setNewRegErr(""); setShowNewRegister(true); }}
                      style={{ background: "none", border: "none", color: C.accent, cursor: "pointer", fontSize: 13, fontWeight: 600 }}>Crear primera caja</button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8 }}>
                    <select value={selRegister} onChange={e => setSelRegister(e.target.value ? Number(e.target.value) : "")}
                      style={{ flex: 1, padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14 }}>
                      <option value="">-- Selecciona --</option>
                      {registers.map(r => (
                        <option key={r.id} value={r.id} disabled={r.has_open_session}>{r.name}{r.has_open_session ? " (ocupada)" : ""}</option>
                      ))}
                    </select>
                    <button type="button" onClick={() => { setNewRegName(""); setNewRegErr(""); setShowNewRegister(true); }}
                      style={{ padding: "9px 14px", borderRadius: C.r, border: `1px solid ${C.border}`, background: C.surface, color: C.accent, fontWeight: 700, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" }}>
                      + Nueva caja
                    </button>
                  </div>
                )}
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.mid, marginBottom: 6 }}>Fondo inicial (efectivo)</div>
                <input value={initialAmt} onChange={e => setInitialAmt(e.target.value)}
                  placeholder="$0" inputMode="decimal"
                  style={{ width: "100%", padding: "9px 12px", border: `1px solid ${C.borderMd}`, borderRadius: C.r, fontSize: 14, boxSizing: "border-box" }} />
              </div>
              <Btn variant="primary" onClick={openSession} disabled={busy || !selRegister} full>
                {busy ? <><Spinner size={14} /> Abriendo...</> : "Abrir arqueo"}
              </Btn>
            </div>
          </div>
        )
      )}

      {/* HISTORY TAB */}
      {tab === "history" && (
        <CajaHistory history={history} histLoad={histLoad} histPage={histPage} histTotal={histTotal} onPageChange={(p) => { setHistPage(p); loadHistory(p); }} />
      )}

      {/* MODALS */}
      {showMove && <AddMovementModal moveType={moveType} setMoveType={setMoveType} moveAmt={moveAmt} setMoveAmt={setMoveAmt} moveDesc={moveDesc} setMoveDesc={setMoveDesc} busy={busy} onClose={() => setShowMove(false)} onSubmit={addMovement} />}
      {showClose && session?.live && <CloseSessionModal live={session.live} countedCash={countedCash} setCountedCash={setCountedCash} closeNote={closeNote} setCloseNote={setCloseNote} busy={busy} onClose={() => setShowClose(false)} onSubmit={closeSession} />}

      {/* New register modal */}
      {showNewRegister && (
        <div
          onClick={() => !newRegBusy && setShowNewRegister(false)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
            zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: C.surface, borderRadius: C.rMd, width: "100%", maxWidth: 420,
              maxHeight: "90vh", overflowY: "auto", boxShadow: C.shMd,
              animation: "fadeIn 0.15s ease",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${C.border}` }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 800, color: C.text }}>Nueva caja</div>
                <div style={{ fontSize: 12, color: C.mute, marginTop: 2 }}>Define el nombre de la caja registradora</div>
              </div>
              <button
                type="button"
                aria-label="Cerrar"
                onClick={() => !newRegBusy && setShowNewRegister(false)}
                style={{ background: "none", border: "none", cursor: "pointer", color: C.mute, padding: 4, display: "flex", borderRadius: 4 }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div style={{ padding: "18px 20px" }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "block", marginBottom: 6 }}>
                Nombre de la caja
              </label>
              <input
                autoFocus
                value={newRegName}
                onChange={(e) => { setNewRegName(e.target.value); if (newRegErr) setNewRegErr(""); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newRegName.trim() && !newRegBusy) {
                    (async () => {
                      setNewRegBusy(true); setNewRegErr("");
                      try {
                        await apiFetch("/caja/registers/", { method: "POST", body: JSON.stringify({ name: newRegName.trim() }) });
                        setShowNewRegister(false);
                        load();
                      } catch (err: any) {
                        setNewRegErr(err?.message ?? "Error al crear la caja");
                      } finally { setNewRegBusy(false); }
                    })();
                  }
                  if (e.key === "Escape" && !newRegBusy) setShowNewRegister(false);
                }}
                placeholder="Caja 1, Barra, Caja rápida..."
                disabled={newRegBusy}
                style={{
                  width: "100%", padding: "11px 14px",
                  border: `1.5px solid ${newRegErr ? C.red : C.border}`,
                  borderRadius: C.r, fontSize: 14, fontFamily: C.font,
                  outline: "none", boxSizing: "border-box",
                }}
              />
              {newRegErr && (
                <div style={{ fontSize: 12, color: C.red, marginTop: 6 }}>{newRegErr}</div>
              )}
              <div style={{ fontSize: 11, color: C.mute, marginTop: 8 }}>
                Podrás crear más cajas después. Cada caja maneja su propio arqueo.
              </div>
            </div>
            <div style={{ padding: "12px 20px 18px", display: "flex", justifyContent: "flex-end", gap: 8, borderTop: `1px solid ${C.border}` }}>
              <Btn variant="secondary" onClick={() => setShowNewRegister(false)} disabled={newRegBusy}>Cancelar</Btn>
              <Btn
                variant="primary"
                disabled={!newRegName.trim() || newRegBusy}
                onClick={async () => {
                  setNewRegBusy(true); setNewRegErr("");
                  try {
                    await apiFetch("/caja/registers/", { method: "POST", body: JSON.stringify({ name: newRegName.trim() }) });
                    setShowNewRegister(false);
                    load();
                  } catch (err: any) {
                    setNewRegErr(err?.message ?? "Error al crear la caja");
                  } finally { setNewRegBusy(false); }
                }}
              >
                {newRegBusy ? <><Spinner size={14} /> Creando...</> : "Crear caja"}
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
