"use client";

import React from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import {
  Modal, ProductCard, FieldGroup, ErrBanner, PreviewRow, Btn,
  iS, toNum, fQty, sanitizePos, sanitizeDelta,
  type StockRow, type Warehouse,
} from "./StockShared";

// ─── Receive Modal ───────────────────────────────────────────────────────────
interface ReceiveModalProps {
  sel: StockRow;
  whName: string;
  recQty: string; setRecQty: (v: string) => void;
  recCost: string; setRecCost: (v: string) => void;
  recNote: string; setRecNote: (v: string) => void;
  recBusy: boolean;
  recErr: string | null; setRecErr: (v: string | null) => void;
  onClose: () => void;
  onSubmit: () => void;
}

export function ReceiveModal({ sel, whName, recQty, setRecQty, recCost, setRecCost, recNote, setRecNote, recBusy, recErr, setRecErr, onClose, onSubmit }: ReceiveModalProps) {
  const recQtyN = toNum(recQty);
  const recCostN = recCost.trim() ? toNum(recCost) : 0;
  const recOk = !isNaN(recQtyN) && recQtyN > 0 && (!recCost.trim() || (!isNaN(recCostN) && recCostN >= 0));

  return (
    <Modal title="Recibir stock" subtitle={`Bodega: ${whName}`} onClose={onClose} disabled={recBusy} accentColor={C.green}>
      <ProductCard row={sel} />
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <FieldGroup label="Cantidad *" err={!isNaN(recQtyN) && recQtyN <= 0 && recQty.trim() ? "Debe ser > 0" : null}>
          <input value={recQty} onChange={e => setRecQty(sanitizePos(e.target.value))} autoFocus inputMode="decimal"
            placeholder="Ej: 10" style={iS({ fontFamily: C.mono })} disabled={recBusy}
            onKeyDown={e => { if (e.key === "Enter") onSubmit(); }} />
        </FieldGroup>
        <FieldGroup label="Costo unitario (opcional)" hint="Usado para costeo promedio ponderado">
          <div style={{ position: "relative" }}>
            <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: C.mute, fontFamily: C.mono, fontSize: 13, pointerEvents: "none" }}>$</span>
            <input value={recCost} onChange={e => setRecCost(sanitizePos(e.target.value))} inputMode="decimal"
              placeholder="0" style={iS({ paddingLeft: 22, fontFamily: C.mono })} disabled={recBusy} />
          </div>
        </FieldGroup>
        <FieldGroup label="Nota">
          <input value={recNote} onChange={e => setRecNote(e.target.value)} style={iS()} disabled={recBusy} />
        </FieldGroup>
      </div>
      {recErr && <ErrBanner msg={recErr} onClose={() => setRecErr(null)} />}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
        <Btn variant="ghost" onClick={onClose} disabled={recBusy}>Cancelar</Btn>
        <Btn variant="success" onClick={onSubmit} disabled={recBusy || !recOk}>
          {recBusy ? <><Spinner size={13} />Guardando...</> : "Confirmar recepcion"}
        </Btn>
      </div>
    </Modal>
  );
}

// ─── Issue Modal ─────────────────────────────────────────────────────────────
interface IssueModalProps {
  sel: StockRow;
  whName: string;
  issQty: string; setIssQty: (v: string) => void;
  issReason: string; setIssReason: (v: string) => void;
  issNote: string; setIssNote: (v: string) => void;
  issBusy: boolean;
  issErr: string | null; setIssErr: (v: string | null) => void;
  onClose: () => void;
  onSubmit: () => void;
}

export function IssueModal({ sel, whName, issQty, setIssQty, issReason, setIssReason, issNote, setIssNote, issBusy, issErr, setIssErr, onClose, onSubmit }: IssueModalProps) {
  const onHand = toNum(sel.on_hand);
  const issQtyN = toNum(issQty);
  const issEst = !isNaN(onHand) && !isNaN(issQtyN) ? onHand - issQtyN : NaN;
  const issNeg = !isNaN(issEst) && issEst < 0;
  const issOk = !isNaN(issQtyN) && issQtyN > 0 && !issNeg;

  return (
    <Modal title="Egresar stock" subtitle={`Bodega: ${whName}`} onClose={onClose} disabled={issBusy} accentColor={C.red}>
      <ProductCard row={sel} />
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <FieldGroup label="Cantidad *" err={issNeg ? "Stock insuficiente" : (!isNaN(issQtyN) && issQtyN <= 0 && issQty.trim() ? "Debe ser > 0" : null)}>
          <input value={issQty} onChange={e => setIssQty(sanitizePos(e.target.value))} autoFocus inputMode="decimal"
            placeholder="Ej: 2" style={iS({ fontFamily: C.mono })} disabled={issBusy}
            onKeyDown={e => { if (e.key === "Enter") onSubmit(); }} />
        </FieldGroup>
        {!isNaN(issQtyN) && issQtyN > 0 && (
          <div style={{ padding: "8px 12px", borderRadius: C.r, background: C.bg, border: `1px solid ${C.border}`, display: "flex", flexDirection: "column", gap: 4 }}>
            <PreviewRow label="Stock actual" value={fQty(sel.on_hand)} />
            <PreviewRow label="Salida" value={`- ${fQty(String(issQtyN))}`} />
            <div style={{ height: 1, background: C.border }} />
            <PreviewRow label="Stock resultante" value={isNaN(issEst) ? "—" : fQty(String(issEst))} highlight={!issNeg} />
            {issNeg && <div style={{ fontSize: 11, color: C.red, fontWeight: 700 }}>⚠️ Stock insuficiente</div>}
          </div>
        )}
        <FieldGroup label="Motivo">
          <select value={issReason} onChange={e => setIssReason(e.target.value)} style={iS({ height: 36 })} disabled={issBusy}>
            <option value="MERMA">MERMA</option>
            <option value="VENCIDO">VENCIDO</option>
            <option value="USO_INTERNO">USO INTERNO</option>
            <option value="OTRO">OTRO</option>
          </select>
        </FieldGroup>
        <FieldGroup label="Nota">
          <input value={issNote} onChange={e => setIssNote(e.target.value)} style={iS()} disabled={issBusy} />
        </FieldGroup>
      </div>
      {issErr && <ErrBanner msg={issErr} onClose={() => setIssErr(null)} />}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
        <Btn variant="ghost" onClick={onClose} disabled={issBusy}>Cancelar</Btn>
        <Btn variant="danger" onClick={onSubmit} disabled={issBusy || !issOk}>
          {issBusy ? <><Spinner size={13} />Guardando...</> : "Confirmar salida"}
        </Btn>
      </div>
    </Modal>
  );
}

// ─── Adjust Modal ────────────────────────────────────────────────────────────
interface AdjustModalProps {
  sel: StockRow;
  whName: string;
  adjQty: string; setAdjQty: (v: string) => void;
  adjCost: string; setAdjCost: (v: string) => void;
  adjNote: string; setAdjNote: (v: string) => void;
  adjBusy: boolean;
  adjErr: string | null; setAdjErr: (v: string | null) => void;
  onClose: () => void;
  onSubmit: () => void;
}

export function AdjustModal({ sel, whName, adjQty, setAdjQty, adjCost, setAdjCost, adjNote, setAdjNote, adjBusy, adjErr, setAdjErr, onClose, onSubmit }: AdjustModalProps) {
  const onHand = toNum(sel.on_hand);
  const adjDelta = toNum(adjQty);
  const adjEst = !isNaN(onHand) && !isNaN(adjDelta) ? onHand + adjDelta : NaN;
  const adjNeg = !isNaN(adjEst) && adjEst < 0;
  const adjOk = !isNaN(adjDelta) && !adjNeg && (adjDelta !== 0 || adjCost.trim() !== "");

  return (
    <Modal title="Ajustar stock" subtitle={`Bodega: ${whName}`} onClose={onClose} disabled={adjBusy} accentColor={C.accent}>
      <ProductCard row={sel} />
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <FieldGroup label="Delta de cantidad (opcional)" hint="Ej: 5 para agregar, -3 para descontar. Deja vacio si solo quieres cambiar el costo."
          err={adjNeg ? "Dejaria el stock negativo" : (!isNaN(adjDelta) && adjDelta === 0 && adjQty.trim() ? "Debe ser distinto de 0" : null)}>
          <input value={adjQty} onChange={e => setAdjQty(sanitizeDelta(e.target.value))} autoFocus inputMode="decimal"
            placeholder="Ej: 10 o -3" style={iS({ fontFamily: C.mono })} disabled={adjBusy}
            onKeyDown={e => { if (e.key === "Enter") onSubmit(); }} />
        </FieldGroup>
        {!isNaN(adjDelta) && adjDelta !== 0 && (
          <div style={{ padding: "8px 12px", borderRadius: C.r, background: C.bg, border: `1px solid ${C.border}`, display: "flex", flexDirection: "column", gap: 4 }}>
            <PreviewRow label="Stock actual" value={fQty(sel.on_hand)} />
            <PreviewRow label="Delta" value={(adjDelta > 0 ? "+" : "") + fQty(String(adjDelta))} />
            <div style={{ height: 1, background: C.border }} />
            <PreviewRow label="Stock resultante" value={isNaN(adjEst) ? "—" : fQty(String(adjEst))} highlight={!adjNeg} />
            {adjNeg && <div style={{ fontSize: 11, color: C.red, fontWeight: 700 }}>⚠️ Quedaria negativo</div>}
          </div>
        )}
        <FieldGroup label="Nuevo costo promedio (opcional)" hint={`Costo actual: ${sel.avg_cost && toNum(sel.avg_cost) > 0 ? "$" + Math.round(toNum(sel.avg_cost)).toLocaleString("es-CL") : "no registrado"} — deja vacio para no modificarlo`}>
          <div style={{ position: "relative" }}>
            <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: C.mute, fontFamily: C.mono, fontSize: 13, pointerEvents: "none" }}>$</span>
            <input value={adjCost} onChange={e => setAdjCost(sanitizePos(e.target.value))} inputMode="decimal"
              placeholder={sel.avg_cost && toNum(sel.avg_cost) > 0 ? String(Math.round(toNum(sel.avg_cost))) : "0"}
              style={iS({ paddingLeft: 22, fontFamily: C.mono })} disabled={adjBusy} />
          </div>
        </FieldGroup>
        <FieldGroup label="Nota">
          <input value={adjNote} onChange={e => setAdjNote(e.target.value)} style={iS()} disabled={adjBusy} />
        </FieldGroup>
      </div>
      {adjErr && <ErrBanner msg={adjErr} onClose={() => setAdjErr(null)} />}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
        <Btn variant="ghost" onClick={onClose} disabled={adjBusy}>Cancelar</Btn>
        <Btn variant="violet" onClick={onSubmit} disabled={adjBusy || !adjOk}>
          {adjBusy ? <><Spinner size={13} />Guardando...</> : "Guardar ajuste"}
        </Btn>
      </div>
    </Modal>
  );
}

// ─── Transfer Modal ──────────────────────────────────────────────────────────
interface TransferModalProps {
  whName: string;
  warehouseId: number | null;
  activeWh: Warehouse[];
  items: StockRow[];
  trTarget: number | null; setTrTarget: (v: number | null) => void;
  trProdId: number | null; setTrProdId: (v: number | null) => void;
  trQty: string; setTrQty: (v: string) => void;
  trNote: string; setTrNote: (v: string) => void;
  trBusy: boolean;
  trErr: string | null; setTrErr: (v: string | null) => void;
  onClose: () => void;
  onSubmit: () => void;
}

export function TransferModal({ whName, warehouseId, activeWh, items, trTarget, setTrTarget, trProdId, setTrProdId, trQty, setTrQty, trNote, setTrNote, trBusy, trErr, setTrErr, onClose, onSubmit }: TransferModalProps) {
  const trQtyN = toNum(trQty);
  const trOk = !isNaN(trQtyN) && trQtyN > 0 && !!trTarget && trTarget !== warehouseId && !!trProdId;

  return (
    <Modal title="Transferir stock" subtitle={`Desde: ${whName}`} onClose={onClose} disabled={trBusy} accentColor={C.sky}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <FieldGroup label="Bodega destino *">
          <select value={trTarget ?? ""} onChange={e => setTrTarget(Number(e.target.value))} style={iS({ height: 36 })} disabled={trBusy}>
            <option value="" disabled>Selecciona...</option>
            {activeWh.filter(w => w.id !== warehouseId).map(w => <option key={w.id} value={w.id}>{w.name}{w.warehouse_type === "sales_floor" ? " (Sala)" : " (Bodega)"}</option>)}
          </select>
        </FieldGroup>
        <FieldGroup label="Producto *">
          <select value={trProdId ?? ""} onChange={e => setTrProdId(Number(e.target.value))} style={iS({ height: 36 })} disabled={trBusy}>
            <option value="" disabled>Selecciona un producto...</option>
            {items.map(r => <option key={r.product_id} value={r.product_id}>{r.name}{r.sku ? ` (${r.sku})` : ""} — Stock: {fQty(r.on_hand)}</option>)}
          </select>
        </FieldGroup>
        <FieldGroup label="Cantidad *">
          <input value={trQty} onChange={e => setTrQty(sanitizePos(e.target.value))} autoFocus inputMode="decimal"
            placeholder="Ej: 5" style={iS({ fontFamily: C.mono })} disabled={trBusy}
            onKeyDown={e => { if (e.key === "Enter") onSubmit(); }} />
        </FieldGroup>
        <FieldGroup label="Nota">
          <input value={trNote} onChange={e => setTrNote(e.target.value)} style={iS()} disabled={trBusy} />
        </FieldGroup>
      </div>
      {trErr && <ErrBanner msg={trErr} onClose={() => setTrErr(null)} />}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
        <Btn variant="ghost" onClick={onClose} disabled={trBusy}>Cancelar</Btn>
        <Btn variant="sky" onClick={onSubmit} disabled={trBusy || !trOk}>
          {trBusy ? <><Spinner size={13} />Procesando...</> : "Confirmar transferencia"}
        </Btn>
      </div>
    </Modal>
  );
}
