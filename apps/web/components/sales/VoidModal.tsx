"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";

export function VoidModal({ saleId, onClose, onDone }: { saleId: number; onClose: ()=>void; onDone: ()=>void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy]     = useState(false);
  const [err, setErr]       = useState<string|null>(null);

  async function doVoid() {
    if (!reason.trim()) { setErr("Debes ingresar un motivo."); return; }
    setBusy(true); setErr(null);
    try {
      await apiFetch(`/sales/sales/${saleId}/void/`, { method:"POST", body:JSON.stringify({ reason: reason.trim() }) });
      onDone();
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.message : (e?.message ?? "No se pudo anular"));
    } finally { setBusy(false); }
  }

  return (
    <div className="bd-in" style={{
      position:"fixed", inset:0, background:"rgba(0,0,0,0.4)",
      display:"grid", placeItems:"center", padding:20, zIndex:60,
    }}>
      <div className="m-in" style={{
        width:"min(520px,100%)", background:C.surface,
        borderRadius:C.rLg, border:`1px solid ${C.border}`,
        boxShadow:C.shLg, overflow:"hidden",
      }}>
        {/* Accent bar */}
        <div style={{ height:3, background:C.red }}/>
        <div style={{ padding:"20px 24px" }}>
          <div style={{ fontSize:15, fontWeight:700, color:C.text, marginBottom:4 }}>Anular venta #{saleId}</div>
          <div style={{ fontSize:13, color:C.mute, marginBottom:16 }}>
            Esta accion revertira el stock de todos los productos. Ingresa un motivo obligatorio.
          </div>

          <label style={{ fontSize:11, fontWeight:700, color:C.mid, textTransform:"uppercase", letterSpacing:"0.06em", display:"block", marginBottom:6 }}>
            Motivo <span style={{ color:C.red }}>*</span>
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ej: Error en el cobro, devolucion del cliente…"
            rows={3}
            disabled={busy}
            autoFocus
            style={{
              width:"100%", padding:"10px 12px", resize:"vertical",
              border:`1px solid ${C.border}`, borderRadius:C.r,
              fontSize:13, fontFamily:C.font, lineHeight:1.55,
            }}
          />

          {err && (
            <div style={{ marginTop:10, padding:"9px 12px", borderRadius:C.r, border:`1px solid ${C.redBd}`, background:C.redBg, color:C.red, fontSize:13 }}>
              {err}
            </div>
          )}

          <div style={{ display:"flex", justifyContent:"flex-end", gap:8, marginTop:16 }}>
            <Btn variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Btn>
            <Btn variant="danger" onClick={doVoid} disabled={busy || !reason.trim()}>
              {busy ? <><Spinner/>Anulando…</> : "Confirmar anulacion"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}
