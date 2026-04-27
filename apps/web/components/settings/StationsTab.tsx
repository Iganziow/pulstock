"use client";
/**
 * Print Stations tab — administra las estaciones de impresión del tenant.
 *
 * Una estación es un destino lógico donde sale un tipo de ticket. Ejemplos
 * típicos: "Cocina", "Bar", "Despacho", "Caja". Cada estación tiene 1+
 * impresoras asignadas; las categorías y productos del catálogo se asocian
 * a estaciones, y el sistema rutea las comandas automáticamente.
 *
 * Si el negocio tiene UNA sola impresora (caso típico cafetería), no hace
 * falta crear estaciones — el flujo "auto-print" sin station_id sigue
 * funcionando como siempre. Las estaciones son útiles cuando hay 2+
 * impresoras (cocina + bar, etc.) o cuando se quiere distinguir
 * cocina/despacho aunque se imprima en la misma máquina.
 */
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { humanizeError } from "@/lib/errors";
import { C } from "@/lib/theme";
import { Card, SectionHeader, Btn, Spinner, Label, Hint, iS, FL } from "./SettingsUI";

interface StationPrinterDTO {
  id: number;
  name: string;
  display_name: string;
  agent_id: number;
  agent_name: string;
  agent_online: boolean;
  connection_type: "system" | "usb" | "network";
  paper_width: 58 | 80;
}
interface StationDTO {
  id: number;
  name: string;
  is_default_for_receipts: boolean;
  sort_order: number;
  printers: StationPrinterDTO[];
}

interface AgentPrinterFlat {
  id: number;
  name: string;
  display_name: string;
  agent_id: number;
  agent_name: string;
  station_id: number | null;
}

interface StationsTabProps {
  mob: boolean;
  flash: (type: "ok" | "err", text: string) => void;
}

export default function StationsTab({ mob, flash }: StationsTabProps) {
  const [stations, setStations] = useState<StationDTO[]>([]);
  const [allPrinters, setAllPrinters] = useState<AgentPrinterFlat[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newIsDefault, setNewIsDefault] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  // assigningStationId: la estación a la que estamos asignando una impresora
  // (muestra el dropdown). null = no se está asignando.
  const [assigningStationId, setAssigningStationId] = useState<number | null>(null);

  const reload = async () => {
    setLoading(true);
    try {
      const [stationsData, agentsData] = await Promise.all([
        apiFetch("/printing/stations/"),
        apiFetch("/printing/agents/"),
      ]);
      setStations(stationsData || []);
      // Aplastar el árbol agents → printers a una lista plana con el
      // station_id actual de cada printer. Esto se usa para el dropdown
      // "asignar impresora a estación X" (mostrando solo las no asignadas
      // a esta estación).
      const flat: AgentPrinterFlat[] = [];
      for (const a of agentsData || []) {
        for (const p of a.printers || []) {
          flat.push({
            id: p.id,
            name: p.display_name || p.name,
            display_name: p.display_name || p.name,
            agent_id: a.id,
            agent_name: a.name,
            station_id: p.station_id ?? null,
          });
        }
      }
      setAllPrinters(flat);
    } catch (e: any) {
      flash("err", humanizeError(e, "Error cargando estaciones"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(); }, []);

  const create = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await apiFetch("/printing/stations/", {
        method: "POST",
        body: JSON.stringify({
          name: newName.trim(),
          is_default_for_receipts: newIsDefault,
          sort_order: stations.length,
        }),
      });
      flash("ok", `Estación "${newName.trim()}" creada`);
      setNewName(""); setNewIsDefault(false); setShowAdd(false);
      await reload();
    } catch (e: any) {
      flash("err", humanizeError(e, "Error al crear estación"));
    } finally {
      setCreating(false);
    }
  };

  const renameStation = async (id: number) => {
    const name = editingName.trim();
    if (!name) { setEditingId(null); return; }
    try {
      await apiFetch(`/printing/stations/${id}/`, {
        method: "PATCH", body: JSON.stringify({ name }),
      });
      setEditingId(null);
      await reload();
      flash("ok", "Nombre actualizado");
    } catch (e: any) {
      flash("err", humanizeError(e, "Error al renombrar"));
    }
  };

  const setDefault = async (id: number) => {
    try {
      await apiFetch(`/printing/stations/${id}/`, {
        method: "PATCH", body: JSON.stringify({ is_default_for_receipts: true }),
      });
      await reload();
      flash("ok", "Estación marcada como destino de boletas");
    } catch (e: any) {
      flash("err", humanizeError(e, "Error al actualizar"));
    }
  };

  const remove = async (s: StationDTO) => {
    if (!confirm(
      `¿Eliminar la estación "${s.name}"?\n\n` +
      `Las categorías y productos que apunten a esta estación quedarán ` +
      `sin destino y caerán al fallback. Las impresoras seguirán existiendo.`,
    )) return;
    try {
      await apiFetch(`/printing/stations/${s.id}/`, { method: "DELETE" });
      flash("ok", `Estación "${s.name}" eliminada`);
      await reload();
    } catch (e: any) {
      flash("err", humanizeError(e, "Error al eliminar"));
    }
  };

  const assignPrinter = async (stationId: number | null, printerId: number) => {
    try {
      await apiFetch(`/printing/printers/${printerId}/station/`, {
        method: "PATCH",
        body: JSON.stringify({ station_id: stationId }),
      });
      setAssigningStationId(null);
      await reload();
      flash("ok", stationId ? "Impresora asignada" : "Impresora desasignada");
    } catch (e: any) {
      flash("err", humanizeError(e, "Error al asignar impresora"));
    }
  };

  const hasDefault = stations.some(s => s.is_default_for_receipts);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Card>
        <SectionHeader
          icon="🏷️"
          title="Estaciones de impresión"
          desc="Define dónde sale cada tipo de ticket. Cocina, bar, despacho, caja… Después asignas categorías o productos del catálogo a cada estación."
        />

        {/* Aviso útil para tenant nuevo */}
        {!loading && stations.length === 0 && (
          <div style={{
            background: C.amberBg, border: `1px solid ${C.amberBd}`,
            borderRadius: 8, padding: "12px 14px", fontSize: 12, color: C.amber,
            lineHeight: 1.5, marginBottom: 12,
          }}>
            <strong>¿Cuándo necesito esto?</strong><br/>
            Si tu negocio tiene <strong>una sola impresora</strong> (caso típico cafetería) podés saltarte esta pestaña — todo se imprime ahí automáticamente.
            <br/><br/>
            Crealas si tenés <strong>2 o más impresoras</strong> (cocina + bar, despacho separado, etc.) o si querés que los tickets de cocina y despacho salgan en hojas distintas aunque sea la misma impresora.
          </div>
        )}

        {/* Aviso si hay estaciones pero ninguna marcada como default para boletas */}
        {!loading && stations.length > 0 && !hasDefault && (
          <div style={{
            background: C.redBg, border: `1px solid ${C.redBd}`,
            borderRadius: 8, padding: "10px 14px", fontSize: 12, color: C.red,
            marginBottom: 12,
          }}>
            ⚠ Ninguna estación está marcada como <strong>destino de boletas</strong>. Las pre-cuentas y boletas no sabrán a dónde ir — marcá la de "Caja" para arreglarlo.
          </div>
        )}

        {loading && (
          <div style={{ textAlign: "center", padding: 32 }}><Spinner /></div>
        )}

        {/* Lista de estaciones */}
        {!loading && stations.map(s => {
          const isEditing = editingId === s.id;
          const printers = s.printers || [];
          // impresoras del tenant que NO están asignadas a esta estación
          // (pueden estar libres o en otra estación). Se permite reasignar.
          const availablePrinters = allPrinters.filter(p => p.station_id !== s.id);
          return (
            <div key={s.id} style={{
              border: `1.5px solid ${s.is_default_for_receipts ? C.accentBd : C.border}`,
              borderRadius: 10, padding: mob ? 12 : 16, marginBottom: 10,
              background: s.is_default_for_receipts ? C.accentBg : C.surface,
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  {isEditing ? (
                    <>
                      <input style={{ ...iS, padding: "5px 10px", fontSize: 14, width: 180 }}
                        value={editingName} autoFocus
                        onChange={e => setEditingName(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter") renameStation(s.id);
                          if (e.key === "Escape") setEditingId(null);
                        }}
                      />
                      <Btn onClick={() => renameStation(s.id)} variant="primary">Guardar</Btn>
                      <Btn onClick={() => setEditingId(null)} variant="secondary">Cancelar</Btn>
                    </>
                  ) : (
                    <>
                      <span style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{s.name}</span>
                      {s.is_default_for_receipts && (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
                          background: C.accent, color: "#fff",
                        }}>
                          BOLETAS / PRE-CUENTAS
                        </span>
                      )}
                    </>
                  )}
                </div>
                {!isEditing && (
                  <div style={{ display: "flex", gap: 6 }}>
                    <Btn variant="secondary" onClick={() => { setEditingId(s.id); setEditingName(s.name); }}>
                      Editar
                    </Btn>
                    {!s.is_default_for_receipts && (
                      <Btn variant="secondary" onClick={() => setDefault(s.id)}>
                        Usar para boletas
                      </Btn>
                    )}
                    <Btn variant="danger" onClick={() => remove(s)}>Eliminar</Btn>
                  </div>
                )}
              </div>

              {/* Impresoras asignadas */}
              <div style={{ marginTop: 10, fontSize: 11, fontWeight: 700, color: C.mute, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Impresoras en esta estación
              </div>
              {printers.length === 0 && (
                <div style={{ marginTop: 4, fontSize: 12, color: C.mute, fontStyle: "italic" }}>
                  Sin impresoras asignadas. Si no asignás ninguna, los tickets de esta estación
                  caen al flujo por defecto (impresora Bluetooth del dispositivo o agente PC).
                </div>
              )}
              {printers.map(p => (
                <div key={p.id} style={{
                  marginTop: 6, padding: "8px 10px", background: C.bg,
                  border: `1px solid ${C.border}`, borderRadius: 8,
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap",
                }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>
                      🖨️ {p.display_name || p.name}
                    </div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 1 }}>
                      en <strong>{p.agent_name}</strong> · {p.connection_type.toUpperCase()} · {p.paper_width}mm ·
                      <span style={{ color: p.agent_online ? C.green : C.red, fontWeight: 600, marginLeft: 4 }}>
                        {p.agent_online ? "● En línea" : "● Desconectada"}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => assignPrinter(null, p.id)}
                    style={{
                      padding: "4px 10px", border: `1px solid ${C.border}`, borderRadius: 6,
                      background: C.surface, color: C.mid, fontSize: 11, fontWeight: 600,
                      cursor: "pointer", fontFamily: "inherit",
                    }}
                  >
                    Quitar
                  </button>
                </div>
              ))}

              {/* Asignar impresora */}
              {assigningStationId === s.id ? (
                <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  <select
                    style={{ ...iS, padding: "6px 10px", fontSize: 13 }}
                    onChange={e => {
                      const v = parseInt(e.target.value, 10);
                      if (Number.isFinite(v) && v > 0) assignPrinter(s.id, v);
                    }}
                    defaultValue=""
                  >
                    <option value="">— Elegir impresora —</option>
                    {availablePrinters.map(p => (
                      <option key={p.id} value={p.id}>
                        {p.display_name || p.name} (en {p.agent_name}){p.station_id ? " — actualmente en otra estación" : ""}
                      </option>
                    ))}
                  </select>
                  <Btn variant="secondary" onClick={() => setAssigningStationId(null)}>Cancelar</Btn>
                </div>
              ) : allPrinters.length > 0 ? (
                <button
                  onClick={() => setAssigningStationId(s.id)}
                  style={{
                    marginTop: 8, padding: "6px 14px", border: `1px dashed ${C.borderMd}`,
                    borderRadius: 6, background: "transparent", color: C.accent,
                    fontSize: 12, fontWeight: 600, cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                >
                  + Asignar impresora
                </button>
              ) : (
                // Mensaje explicativo cuando NO hay agent printers — caso típico
                // de Mario: usa solo Bluetooth desde el celular, no tiene PC con
                // agente. Le explicamos por qué no puede asignar y qué pasa.
                <div style={{
                  marginTop: 8, padding: "8px 10px",
                  background: C.bg, border: `1px dashed ${C.border}`, borderRadius: 6,
                  fontSize: 11, color: C.mute, lineHeight: 1.5,
                }}>
                  <strong>No hay impresoras de PC para asignar.</strong> Si solo usás impresoras Bluetooth conectadas a un celular o tablet, dejá la estación sin impresora — los tickets saldrán igual en la BT del dispositivo que mande la comanda. Para asignar impresoras dedicadas por estación, necesitás un PC con el <em>Pulstock Printer Agent</em> (descargable en <span style={{ fontFamily: "monospace", color: C.accent }}>pulstock.cl/agent</span>).
                </div>
              )}
            </div>
          );
        })}

        {/* Crear nueva estación */}
        {!loading && (
          <div style={{ marginTop: 6 }}>
            {!showAdd ? (
              <Btn onClick={() => setShowAdd(true)} variant="primary">
                + Nueva estación
              </Btn>
            ) : (
              <div style={{ border: `1.5px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Nueva estación</div>
                <div style={FL}>
                  <Label req>Nombre</Label>
                  <input
                    style={iS} value={newName}
                    onChange={e => setNewName(e.target.value)}
                    placeholder="Ej: Cocina, Bar, Despacho, Caja"
                    autoFocus
                  />
                  <Hint>Usa nombres cortos. Una vez creada, los podés usar en Catálogo → Categorías.</Hint>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, cursor: "pointer", fontSize: 13, color: C.mid }}>
                  <input
                    type="checkbox" checked={newIsDefault}
                    onChange={e => setNewIsDefault(e.target.checked)}
                    style={{ accentColor: C.accent, width: 16, height: 16 }}
                  />
                  Esta estación recibe boletas y pre-cuentas
                  {hasDefault && newIsDefault && (
                    <span style={{ fontSize: 11, color: C.amber, marginLeft: 4 }}>
                      (reemplazará la actual)
                    </span>
                  )}
                </label>
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <Btn onClick={create} disabled={creating || !newName.trim()} variant="primary">
                    {creating ? "Creando..." : "Crear"}
                  </Btn>
                  <Btn onClick={() => { setShowAdd(false); setNewName(""); setNewIsDefault(false); }} variant="secondary">
                    Cancelar
                  </Btn>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Tip de uso */}
      <Card>
        <div style={{ fontSize: 13, color: C.mid, lineHeight: 1.6 }}>
          <strong>Cómo usar las estaciones:</strong>
          <ol style={{ margin: "6px 0 0 18px", padding: 0 }}>
            <li>Crea acá tus estaciones (ej: "Cocina", "Bar", "Caja").</li>
            <li>Asigná al menos una impresora a cada estación. La impresora debe estar primero pareada en la pestaña <em>Impresoras</em>.</li>
            <li>Marcá una estación como <strong>destino de boletas</strong> (típicamente "Caja"). Las boletas y pre-cuentas siempre van ahí.</li>
            <li>En <em>Catálogo → Categorías</em>, asocia cada categoría a su estación. Ejemplo: categoría "Bebidas" → estación "Bar".</li>
            <li>Al imprimir una comanda, el sistema agrupa los items por estación y manda un ticket separado a cada impresora.</li>
          </ol>
        </div>
      </Card>
    </div>
  );
}
