"use client";

import React from "react";
import { C } from "@/lib/theme";
import { Btn, Spinner } from "@/components/ui";
import { REASONS } from "./SalidasLinesTable";

interface SalidasSummaryProps {
  mob: boolean;
  linesCount: number;
  totalQty: number;
  invalidCount: number;
  canSubmit: boolean;
  submitting: boolean;
  globalReason: string;
  globalNote: string;
  onSubmit: () => void;
}

export function SalidasSummary({ mob, linesCount, totalQty, invalidCount, canSubmit, submitting, globalReason, globalNote, onSubmit }: SalidasSummaryProps) {
  return (
    <div style={{ position: mob ? "relative" : "sticky", top: mob ? undefined : 24 }}>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: "16px 20px", boxShadow: C.sh }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 14 }}>Resumen</div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 13, color: C.mute }}>Productos</span>
            <span style={{ fontSize: 14, fontWeight: 700, fontFamily: C.mono }}>{linesCount}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 13, color: C.mute }}>Unidades a egresar</span>
            <span style={{ fontSize: 14, fontWeight: 700, fontFamily: C.mono, color: totalQty > 0 ? C.red : C.text }}>
              {totalQty > 0 ? `- ${totalQty.toLocaleString("es-CL", { maximumFractionDigits: 3 })}` : "0"}
            </span>
          </div>
          {invalidCount > 0 && (
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: 13, color: C.red, fontWeight: 600 }}>Con errores</span>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: C.mono, color: C.red }}>{invalidCount}</span>
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
          <Btn variant="danger" full onClick={onSubmit} disabled={!canSubmit || submitting} size="lg">
            {submitting ? <><Spinner size={14} /> Procesando...</> : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                Confirmar salida ({linesCount})
              </>
            )}
          </Btn>
        </div>

        {linesCount > 0 && !canSubmit && !submitting && (
          <div style={{ fontSize: 11, color: C.amber, fontWeight: 600, marginTop: 8, textAlign: "center" }}>
            Completa las cantidades de todos los productos
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Progress Overlay ────────────────────────────────────────────────────────
interface ProgressOverlayProps {
  submitting: boolean;
  done: number;
  total: number;
}

export function SalidasProgressOverlay({ submitting, done, total }: ProgressOverlayProps) {
  if (!submitting) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "grid", placeItems: "center", zIndex: 100 }}>
      <div style={{ background: C.surface, borderRadius: C.rLg, padding: "28px 36px", textAlign: "center", boxShadow: C.shLg, minWidth: 280 }}>
        <Spinner size={28} />
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginTop: 14 }}>Procesando salida...</div>
        <div style={{ fontSize: 13, color: C.mute, marginTop: 6 }}>{done} de {total} productos</div>
        <div style={{ width: "100%", height: 6, background: C.bg, borderRadius: 3, marginTop: 12, overflow: "hidden" }}>
          <div style={{ height: "100%", background: C.accent, borderRadius: 3, transition: "width 0.3s ease", width: `${total ? (done / total) * 100 : 0}%` }} />
        </div>
      </div>
    </div>
  );
}
