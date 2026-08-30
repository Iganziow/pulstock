"use client";

import React, { useState } from "react";
import { C } from "@/lib/theme";
import { Spinner } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import {
  Modal, FieldGroup, ErrBanner, Btn, iS, toNum, fQty, sanitizePos,
  type StockRow,
} from "./StockShared";

/**
 * Ventas sin sistema — el pedido textual de Mario:
 *
 *   "Poder ajustar inventario tras periodos de venta sin sistema de larga
 *    duración (corte de luz, caída), de manera que no afecte las ventas del
 *    turno en que se realice la actualización."
 *
 * El backend fecha el consumo en el DÍA DEL CORTE (el turno actual queda
 * limpio) y lo marca como demanda para que el modelo aprenda de ese día en
 * vez de creer que no se vendió nada. Esta pantalla es la parte que faltaba:
 * el endpoint existía y nadie podía usarlo sin curl.
 *
 * Autocontenido a propósito: los modales viejos de esta carpeta arrastran
 * doce props de estado desde la página. Este maneja el suyo y solo pide lo
 * que no puede saber: los productos, la bodega, y qué hacer al terminar.
 */

type Linea = { product_id: number | ""; qty: string };

type Resultado = {
  fecha: string;
  lineas: { nombre: string; qty: string; stock_resultante: string }[];
  descuadres: { nombre: string; faltante: string }[];
};

export function OfflineSalesModal({ items, warehouseId, whName, onClose, onDone }: {
  items: StockRow[];
  warehouseId: number;
  whName: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const hoy = new Date();
  const ayer = new Date(hoy.getTime() - 24 * 3600 * 1000);
  const aISO = (d: Date) => d.toISOString().slice(0, 10);
  const hace60 = new Date(hoy.getTime() - 60 * 24 * 3600 * 1000);

  const [fecha, setFecha] = useState(aISO(ayer));
  const [nota, setNota] = useState("");
  const [lineas, setLineas] = useState<Linea[]>([{ product_id: "", qty: "" }]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);

  const setLinea = (i: number, cambio: Partial<Linea>) =>
    setLineas(ls => ls.map((l, j) => (j === i ? { ...l, ...cambio } : l)));

  const completas = lineas.filter(l => l.product_id !== "" && toNum(l.qty) > 0);
  const listo = completas.length > 0 && !!fecha;

  async function enviar() {
    setErr(null);
    setBusy(true);
    try {
      const r = await apiFetch("/inventory/offline-sales/", {
        method: "POST",
        body: JSON.stringify({
          date: fecha,
          warehouse_id: warehouseId,
          note: nota.trim(),
          lines: completas.map(l => ({ product_id: l.product_id, qty: l.qty })),
        }),
      });
      setResultado(r as Resultado);
    } catch (e: unknown) {
      const d = (e as { data?: { detail?: string } })?.data;
      setErr(d?.detail || "No se pudo registrar. Revisa la conexión e intenta de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  if (resultado) {
    return (
      <Modal title="Ventas registradas" subtitle={`Día del corte: ${resultado.fecha}`}
        onClose={() => { onClose(); onDone(); }} accentColor={C.green}
        footer={<Btn variant="primary" onClick={() => { onClose(); onDone(); }}>Listo</Btn>}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {resultado.lineas.map((l, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 13.5 }}>
              <span>{l.nombre}</span>
              <span style={{ fontFamily: C.mono }}>−{fQty(l.qty)} → quedan {fQty(l.stock_resultante)}</span>
            </div>
          ))}
          {resultado.descuadres.length > 0 && (
            <div style={{
              background: C.amberBg, border: `1px solid ${C.amberBd}`,
              borderRadius: C.r, padding: "10px 12px", fontSize: 13, color: C.amber, lineHeight: 1.55,
            }}>
              <strong>Ojo:</strong> lo declarado superaba el stock del sistema en{" "}
              {resultado.descuadres.map(d => `${d.nombre} (${fQty(d.faltante)})`).join(", ")}.
              El stock quedó en cero y la venta se registró completa — significa que el
              inventario ya estaba descuadrado <em>antes</em> del corte. Vale la pena
              hacer un conteo físico de esos productos.
            </div>
          )}
          <p style={{ fontSize: 12.5, color: C.mute, margin: 0, lineHeight: 1.5 }}>
            El consumo quedó fechado el día del corte: el turno de hoy no se ve
            afectado, y la predicción va a aprender la demanda real de ese día.
          </p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Ventas sin sistema" subtitle={`Bodega: ${whName}`} onClose={onClose}
      accentColor={C.amber} width={620}
      footer={<>
        <Btn variant="ghost" onClick={onClose} disabled={busy}>Cancelar</Btn>
        <Btn variant="primary" onClick={enviar} disabled={busy || !listo}>
          {busy ? <><Spinner size={13} />Registrando...</> : `Registrar ${completas.length || ""} venta${completas.length === 1 ? "" : "s"}`}
        </Btn>
      </>}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <p style={{ fontSize: 13, color: C.mid, margin: 0, lineHeight: 1.55 }}>
          Para cuando se vendió con el sistema caído (corte de luz, sin internet).
          El stock se descuenta <strong>en el día del corte</strong>, así que el
          turno de hoy queda limpio y la predicción aprende lo que realmente se
          vendió ese día.
        </p>

        <FieldGroup label="Día del corte *" hint="Hasta 60 días atrás">
          <input type="date" value={fecha} min={aISO(hace60)} max={aISO(hoy)}
            onChange={e => setFecha(e.target.value)} style={iS({ height: 36 })} disabled={busy} />
        </FieldGroup>

        <FieldGroup label="Qué se vendió *">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {lineas.map((l, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <select value={l.product_id} onChange={e => setLinea(i, { product_id: Number(e.target.value) })}
                  style={iS({ height: 36, flex: 1 })} disabled={busy}>
                  <option value="" disabled>Producto...</option>
                  {items.map(r => (
                    <option key={r.product_id} value={r.product_id}>
                      {r.name}{r.sku ? ` (${r.sku})` : ""} — Stock: {fQty(r.on_hand)}
                    </option>
                  ))}
                </select>
                <input value={l.qty} onChange={e => setLinea(i, { qty: sanitizePos(e.target.value) })}
                  placeholder="Cant." inputMode="decimal"
                  style={iS({ fontFamily: C.mono, width: 90 })} disabled={busy} />
                {lineas.length > 1 && (
                  <button type="button" aria-label="Quitar línea" disabled={busy}
                    onClick={() => setLineas(ls => ls.filter((_, j) => j !== i))}
                    style={{
                      background: "none", border: "none", cursor: "pointer",
                      color: C.mute, fontSize: 16, padding: 4, lineHeight: 1,
                    }}>×</button>
                )}
              </div>
            ))}
            <button type="button" disabled={busy}
              onClick={() => setLineas(ls => [...ls, { product_id: "", qty: "" }])}
              style={{
                alignSelf: "flex-start", background: "none", cursor: "pointer",
                border: `1px dashed ${C.borderMd}`, borderRadius: C.r,
                padding: "6px 12px", fontSize: 13, color: C.mid, fontFamily: "inherit",
              }}>+ Agregar producto</button>
          </div>
        </FieldGroup>

        <FieldGroup label="Nota">
          <input value={nota} onChange={e => setNota(e.target.value)}
            placeholder="Ej: corte de luz de 14:00 a 19:00" style={iS()} disabled={busy} />
        </FieldGroup>
      </div>
      {err && <ErrBanner msg={err} onClose={() => setErr(null)} />}
    </Modal>
  );
}
