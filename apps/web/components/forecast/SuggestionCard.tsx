"use client";

import React from "react";
import Link from "next/link";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { formatQty, fmtQty, type UnitInfo } from "./helpers";

// ─── Types ───────────────────────────────────────────────────────────────────
export type SugLine = {
  product_id: number; product_name: string;
  /** Código de unidad del producto (UN, GR, ML…). Lo manda el backend desde
   *  el 04/09/26; si falta, se asume unidad. */
  unit?: string | null;
  current_stock: string; avg_daily_demand: string; days_to_stockout: number | null;
  suggested_qty: string; estimated_cost: string; reasoning: string;
};
export type Suggestion = { id: number; warehouse_id: number; supplier_name: string; status: string; priority: string; total_estimated: string; generated_at: string; approved_at: string | null; purchase_id: number | null; lines_count: number; lines: SugLine[] };

// ─── Formatters ──────────────────────────────────────────────────────────────
const fmtMoney = (v: string | number) => { const n = typeof v === "string" ? parseFloat(v) : v; return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL"); };
const unitOf = (l: SugLine): UnitInfo => ({ unit_code: l.unit || "UN" });

// ─── Helpers ─────────────────────────────────────────────────────────────────
function dtoColor(dto: number | null): string {
  if (dto === null) return C.green;
  if (dto <= 3) return C.red;
  if (dto <= 7) return C.amber;
  return C.accent;
}

function dtoLabel(dto: number | null): string {
  if (dto === null) return "Estable";
  if (dto === 0) return "Sin stock";
  if (dto === 1) return "Se acaba en 1 día";
  return `Se acaba en ${dto} días`;
}

function priorityColor(p: string): string {
  return p === "CRITICAL" ? C.red : p === "HIGH" ? C.amber : C.accent;
}
/** Se mantiene por compatibilidad; ya no devuelve un emoji sino un punto de color. */
export function priorityIcon(p: string) {
  return <span aria-hidden style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: priorityColor(p) }} />;
}
export function priorityShort(p: string) { return p === "CRITICAL" ? "Urgente" : p === "HIGH" ? "Importante" : "Preventivo"; }

function priorityDesc(p: string, linesCount: number, critCount: number) {
  if (p === "CRITICAL") return `Atención: ${critCount} producto${critCount > 1 ? "s" : ""} requiere reposición inmediata.`;
  if (p === "HIGH") return `${linesCount} producto${linesCount > 1 ? "s" : ""} próximo a agotarse esta semana.`;
  return `Sugerencia de compra preventiva para ${linesCount} producto${linesCount > 1 ? "s" : ""}.`;
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden style={{ verticalAlign: "-3px", marginRight: 6 }}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

// ─── SuggestionCard ──────────────────────────────────────────────────────────
interface SuggestionCardProps {
  s: Suggestion;
  expanded: boolean;
  onToggle: () => void;
  mob: boolean;
  acting: number | null;
  onConfirmAction: (action: { id: number; action: "approve" | "dismiss" }) => void;
}

export function SuggestionCard({ s, expanded, onToggle, mob, acting, onConfirmAction }: SuggestionCardProps) {
  const isPending = s.status === "PENDING";
  const isApproved = s.status === "APPROVED";
  const isActing = acting === s.id;
  const critLines = s.lines.filter(l => l.days_to_stockout !== null && l.days_to_stockout <= 3);

  return (
    <div style={{ background: C.surface, borderRadius: C.r, boxShadow: C.sh, border: `1px solid ${C.border}`, overflow: "hidden" }}>
      {/* CARD HEADER */}
      <div onClick={onToggle} className="sug-header" style={{ padding: mob ? "16px" : "20px 24px", cursor: "pointer", display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              {priorityIcon(s.priority)}
              <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>{priorityShort(s.priority)}</span>
              {isApproved && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 12, background: C.greenBg, color: C.green }}>Aprobado</span>}
              {s.status === "DISMISSED" && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 12, background: C.bg, color: C.mute }}>Descartado</span>}
            </div>
            <div style={{ fontSize: 14, color: C.mute }}>{priorityDesc(s.priority, s.lines_count, critLines.length)}</div>
          </div>
          <div style={{ width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: expanded ? C.bg : "transparent", transition: "transform .2s", transform: expanded ? "rotate(180deg)" : "rotate(0)", color: C.mute }}>▾</div>
        </div>
        {/* Sin el total de "Unidades": sumar gramos de chocolate con cajas de
            té no significa nada. Productos y costo sí se pueden sumar. */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 24, paddingTop: 8, borderTop: `1px dashed ${C.border}` }}>
          <div><div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Productos</div><div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{s.lines_count}</div></div>
          <div><div style={{ fontSize: 11, color: C.mute, textTransform: "uppercase", letterSpacing: ".05em" }}>Costo total</div><div style={{ fontSize: 16, fontWeight: 600, marginTop: 2, color: C.text }}>{fmtMoney(s.total_estimated)}</div></div>
        </div>
      </div>

      {/* EXPANDED AREA */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${C.border}` }}>
          {s.lines.map((l, i) => {
            const dto = l.days_to_stockout;
            const isUrgent = dto !== null && dto <= 3;
            const isLast = i === s.lines.length - 1;
            const u = unitOf(l);
            // Cantidad sugerida en la unidad del producto: "453 g", "1,2 kg",
            // "30 unidades". Antes decía "453 u." para gramos.
            const qty = formatQty(l.suggested_qty, u, { unitWord: "unidades" });
            return (
              <div key={l.product_id} style={{ padding: mob ? "16px" : "20px 24px", borderBottom: isLast ? "none" : `1px solid ${C.border}`, display: "flex", flexDirection: mob ? "column" : "row", justifyContent: "space-between", alignItems: mob ? "flex-start" : "center", gap: mob ? 16 : 24, background: isUrgent ? C.redBg : C.bg, transition: "background 0.2s" }}>
                <div style={{ flex: 1, width: "100%" }}>
                  <div style={{ fontWeight: 600, fontSize: 15, color: C.text }}>{l.product_name}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 6, fontSize: 13, color: C.mute }}>
                    <span>En bodega: <b style={{ color: C.text }}>{fmtQty(l.current_stock, u)}</b></span>
                    <span style={{ color: dtoColor(dto), fontWeight: 600 }}>{dtoLabel(dto)}</span>
                  </div>
                  <div style={{ marginTop: 10, fontSize: 13, color: C.mid, background: isUrgent ? "#FFFFFF" : C.surface, padding: "10px 14px", borderRadius: 8, borderLeft: `3px solid ${C.accent}`, boxShadow: C.sh, lineHeight: 1.5 }}>
                    <b>¿Por qué pedir {fmtQty(l.suggested_qty, u)}?</b> {l.reasoning}
                  </div>
                </div>
                <div style={{ textAlign: mob ? "left" : "right", minWidth: mob ? "100%" : 140, background: mob ? C.surface : "transparent", padding: mob ? "12px 16px" : 0, borderRadius: mob ? 8 : 0, border: mob ? `1px solid ${C.border}` : "none", display: mob ? "flex" : "block", justifyContent: mob ? "space-between" : "initial", alignItems: mob ? "center" : "initial" }}>
                  <div>
                    <div style={{ fontSize: 12, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: mob ? 2 : 4 }}>Sugerencia</div>
                    <div style={{ fontWeight: 700, fontSize: mob ? 20 : 24, color: C.text }} title={qty.tooltip}>
                      {qty.text} <span style={{ fontSize: 14, fontWeight: 500, color: C.mute }}>{(qty.suffix || "").trim()}</span>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    {mob && <div style={{ fontSize: 11, color: C.mute, marginBottom: 2 }}>Subtotal</div>}
                    <div style={{ fontSize: 15, fontWeight: 600, color: C.amber, marginTop: mob ? 0 : 4 }}>{fmtMoney(l.estimated_cost)}</div>
                  </div>
                </div>
              </div>
            );
          })}

          {isPending && (
            <div style={{ padding: mob ? "16px" : "20px 24px", background: C.surface, display: "flex", justifyContent: "flex-end", gap: 12, borderTop: `1px solid ${C.border}` }}>
              <button type="button" onClick={e => { e.stopPropagation(); onConfirmAction({ id: s.id, action: "dismiss" }); }} disabled={isActing} className="btn-dismiss"
                style={{ padding: "10px 20px", fontSize: 14, fontWeight: 500, cursor: "pointer", background: "transparent", border: `1px solid ${C.border}`, borderRadius: 8, color: C.mid, transition: "all .2s" }}>Descartar</button>
              <button type="button" onClick={e => { e.stopPropagation(); onConfirmAction({ id: s.id, action: "approve" }); }} disabled={isActing} className="btn-approve"
                style={{ padding: "10px 24px", fontSize: 14, fontWeight: 600, cursor: "pointer", background: C.accent, border: "none", borderRadius: 8, color: "#fff", display: "inline-flex", alignItems: "center", gap: 8, transition: "all .2s" }}>
                {isActing ? <><Spinner size={16} /> Procesando...</> : "Aprobar pedido"}
              </button>
            </div>
          )}

          {isApproved && s.purchase_id && (
            <div style={{ padding: mob ? "16px" : "20px 24px", background: C.greenBg, display: "flex", flexDirection: mob ? "column" : "row", justifyContent: "space-between", alignItems: mob ? "flex-start" : "center", gap: 16, borderTop: `1px solid ${C.greenBd}` }}>
              <div style={{ fontSize: 14, color: C.green, fontWeight: 500 }}><CheckIcon /><b>Borrador creado.</b> Esta sugerencia ya fue convertida en una orden de compra.</div>
              <Link href={`/dashboard/purchases`} style={{ padding: "10px 20px", fontSize: 14, fontWeight: 600, background: C.green, color: "#fff", border: "none", borderRadius: 8, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 8, transition: "filter .2s" }} className="btn-approve">
                Ver y editar orden #{s.purchase_id} →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Confirm Modal ───────────────────────────────────────────────────────────
interface ConfirmModalProps {
  suggestion: Suggestion;
  action: "approve" | "dismiss";
  mob: boolean;
  acting: number | null;
  onClose: () => void;
  onApprove: (id: number) => void;
  onDismiss: (id: number) => void;
}

export function SuggestionConfirmModal({ suggestion, action, mob, acting, onClose, onApprove, onDismiss }: ConfirmModalProps) {
  const isApprove = action === "approve";
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.3)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", padding: 16, animation: "fadeIn .2s ease-out" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: C.surface, borderRadius: 16, padding: mob ? "24px" : "32px", maxWidth: 400, width: "100%", boxShadow: "0 20px 25px -5px rgba(0,0,0,.1)", animation: "slideUp .2s ease-out" }}>
        <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 12, color: C.text }}>
          {isApprove ? "Aprobar pedido" : "Descartar sugerencia"}
        </div>
        <div style={{ fontSize: 14, color: C.mute, lineHeight: 1.5, marginBottom: 24 }}>
          {isApprove ? `Crearemos un borrador de compra por ${fmtMoney(suggestion.total_estimated)}. Podrás revisarlo antes de enviarlo.` : "Ocultaremos esta sugerencia. El sistema generará una nueva si el stock vuelve a ser crítico."}
        </div>
        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button type="button" onClick={onClose} style={{ padding: "10px 16px", fontSize: 14, fontWeight: 500, background: "transparent", border: "none", color: C.mute, cursor: "pointer", flex: mob ? "1 1 auto" : "initial" }}>Cancelar</button>
          <button type="button" onClick={() => isApprove ? onApprove(suggestion.id) : onDismiss(suggestion.id)} disabled={acting === suggestion.id} style={{ padding: "10px 20px", fontSize: 14, fontWeight: 600, background: isApprove ? C.accent : C.red, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, flex: mob ? "1 1 auto" : "initial" }}>
            {acting === suggestion.id ? <><Spinner size={16} /> Cargando...</> : isApprove ? "Confirmar" : "Sí, descartar"}
          </button>
        </div>
      </div>
    </div>
  );
}
