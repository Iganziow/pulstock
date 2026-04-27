"use client";
import { useEffect, useState } from "react";
import { C } from "@/lib/theme";
import type { PrinterConfig, PrinterType } from "@/lib/printer";
import {
  getSavedPrinters, getDefaultPrinter, savePrinter, removePrinter,
  setDefaultPrinter, generateId, pairUSBPrinter, pairBluetoothPrinter,
  testNetworkPrinter, printSystemReceipt, printBytes,
} from "@/lib/printer";
import { apiFetch } from "@/lib/api";
import { humanizeError } from "@/lib/errors";
import { EscPos } from "@/lib/escpos";
import { Card, SectionHeader, Divider, Btn, Spinner, Label, Hint, iS, FL } from "./SettingsUI";

// Escape HTML for safe interpolation in receipt test prints.
function esc(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ── Types for agent API ──────────────────────────────────────────────
interface AgentPrinterDTO {
  id: number;
  name: string;
  display_name: string;
  connection_type: "system" | "usb" | "network";
  paper_width: 58 | 80;
  network_address: string;
  is_default: boolean;
}
interface AgentDTO {
  id: number;
  name: string;
  is_online: boolean;
  is_pairing_pending: boolean;
  last_seen_at: string | null;
  version: string;
  os_info: string;
  printers_count: number;
  printers: AgentPrinterDTO[];
}

function fmtLastSeen(iso: string | null): string {
  if (!iso) return "Nunca";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "hace segundos";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  return `hace ${Math.floor(diff / 86400)} d`;
}

interface PrintersTabProps {
  mob: boolean;
  flash: (type: "ok" | "err", text: string) => void;
}

export default function PrintersTab({ mob, flash }: PrintersTabProps) {
  const [printers, setPrinters] = useState<PrinterConfig[]>([]);
  const [defaultId, setDefaultId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addType, setAddType] = useState<PrinterType | null>(null);
  const [addName, setAddName] = useState("");
  const [addWidth, setAddWidth] = useState<58 | 80>(80);
  const [addAddress, setAddAddress] = useState("");
  const [pairing, setPairing] = useState(false);

  const reload = () => {
    try {
      setPrinters(getSavedPrinters());
      setDefaultId(getDefaultPrinter()?.id || null);
    } catch { setPrinters([]); }
  };

  useEffect(() => { reload(); }, []);

  const handleRemove = (id: string) => {
    if (!confirm("¿Eliminar esta impresora?")) return;
    removePrinter(id);
    reload();
    flash("ok", "Impresora eliminada");
  };

  const handleSetDefault = (id: string) => {
    setDefaultPrinter(id);
    setDefaultId(id);
    flash("ok", "Impresora predeterminada actualizada");
  };

  const handleTest = async (p: PrinterConfig) => {
    try {
      if (p.type === "system") {
        const html = `
          <div class="title">PRUEBA</div>
          <div class="sep-double"></div>
          <div class="row"><span>Impresora:</span><span>${esc(p.name)}</span></div>
          <div class="row"><span>Tipo:</span><span>${esc(p.type.toUpperCase())}</span></div>
          <div class="row"><span>Ancho:</span><span>${p.paperWidth}mm</span></div>
          <div class="sep-double"></div>
          <div class="center">Impresión OK!</div>
        `;
        printSystemReceipt(html, p);
        flash("ok", "Prueba enviada al diálogo de impresión");
      } else {
        const cols = p.paperWidth === 58 ? 32 : 48;
        const esc = new EscPos();
        esc.init()
          .align("center").bold(true).fontSize(2, 2)
          .text("PRUEBA").nl()
          .fontSize(1, 1).bold(false)
          .separator("=", cols)
          .textLine("Impresora:", p.name, cols)
          .textLine("Tipo:", p.type.toUpperCase(), cols)
          .textLine("Ancho:", `${p.paperWidth}mm`, cols)
          .separator("=", cols)
          .align("center")
          .text("Impresion OK!").nl()
          .feed(3).cut();
        await printBytes(esc.build(), p);
        flash("ok", "Prueba enviada correctamente");
      }
    } catch (e: any) {
      flash("err", humanizeError(e, "Error al imprimir prueba"));
    }
  };

  const resetAddForm = () => {
    setShowAdd(false); setAddType(null); setAddName(""); setAddAddress(""); setAddWidth(80);
  };

  const handleAddUSB = async () => {
    setPairing(true);
    try {
      await pairUSBPrinter();
      const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora USB", type: "usb", paperWidth: addWidth };
      savePrinter(cfg);
      reload();
      resetAddForm();
      flash("ok", "Impresora USB agregada");
    } catch (e: any) {
      flash("err", humanizeError(e, "No se pudo conectar la impresora USB"));
    } finally { setPairing(false); }
  };

  const handleAddBluetooth = async () => {
    setPairing(true);
    try {
      await pairBluetoothPrinter();
      const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora Bluetooth", type: "bluetooth", paperWidth: addWidth };
      savePrinter(cfg);
      reload();
      resetAddForm();
      flash("ok", "Impresora Bluetooth agregada");
    } catch (e: any) {
      flash("err", humanizeError(e, "No se pudo conectar la impresora Bluetooth"));
    } finally { setPairing(false); }
  };

  const handleAddNetwork = () => {
    if (!addAddress.trim()) { flash("err", "Ingresa la dirección IP"); return; }
    const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora Red", type: "network", paperWidth: addWidth, address: addAddress.trim() };
    savePrinter(cfg);
    reload();
    resetAddForm();
    flash("ok", "Impresora de red agregada");
  };

  const handleTestNetworkConnection = async () => {
    if (!addAddress.trim()) { flash("err", "Ingresa la dirección IP primero"); return; }
    setPairing(true);
    try {
      const result = await testNetworkPrinter(addAddress.trim());
      if (result.ok) {
        flash("ok", "✓ Conexión exitosa — la impresora responde");
      } else {
        flash("err", result.error || "No se pudo conectar a la impresora");
      }
    } catch (e: any) {
      flash("err", humanizeError(e, "Error al probar la conexión"));
    } finally { setPairing(false); }
  };

  const handleAddSystem = () => {
    const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora del sistema", type: "system", paperWidth: addWidth };
    savePrinter(cfg);
    reload();
    resetAddForm();
    flash("ok", "Impresora del sistema agregada");
  };

  const TYPE_BADGES: Record<PrinterType, { label: string; color: string; bg: string; bd: string }> = {
    usb: { label: "USB", color: C.accent, bg: C.accentBg, bd: C.accentBd },
    bluetooth: { label: "Bluetooth", color: "#2563EB", bg: "#EFF6FF", bd: "#BFDBFE" },
    network: { label: "Red/WiFi", color: C.green, bg: C.greenBg, bd: C.greenBd },
    system: { label: "Sistema", color: "#7C3AED", bg: "#F5F3FF", bd: "#DDD6FE" },
    agent: { label: "Agente PC", color: "#DC2626", bg: "#FEF2F2", bd: "#FECACA" },
  };

  // ── Agents state ────────────────────────────────────────────────
  const [agents, setAgents] = useState<AgentDTO[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [showAddAgent, setShowAddAgent] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [creatingAgent, setCreatingAgent] = useState(false);
  const [pairingInfo, setPairingInfo] = useState<{
    agentId: number; name: string; code: string; expires_at: string;
  } | null>(null);
  const [agentsLoadError, setAgentsLoadError] = useState<string | null>(null);

  const reloadAgents = async () => {
    setLoadingAgents(true);
    try {
      const data = (await apiFetch("/printing/agents/")) as AgentDTO[];
      setAgents(Array.isArray(data) ? data : []);
      setAgentsLoadError(null);
    } catch (e: any) {
      // Distinguir "sin agentes" de "error cargando" — importante para UX
      setAgentsLoadError(e?.message || "No se pudieron cargar los agentes");
    } finally {
      setLoadingAgents(false);
    }
  };

  useEffect(() => {
    reloadAgents();
    // Auto-refresh every 10s while tab is open so online status updates
    const t = setInterval(reloadAgents, 10000);
    return () => clearInterval(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateAgent = async () => {
    const name = newAgentName.trim();
    if (!name) { flash("err", "Ingresa un nombre para el agente"); return; }
    setCreatingAgent(true);
    try {
      const resp = (await apiFetch("/printing/agents/", {
        method: "POST", body: JSON.stringify({ name }),
      })) as { id: number; name: string; pairing_code: string; pairing_expires_at: string };
      setPairingInfo({
        agentId: resp.id, name: resp.name,
        code: resp.pairing_code, expires_at: resp.pairing_expires_at,
      });
      setShowAddAgent(false);
      setNewAgentName("");
      await reloadAgents();
      flash("ok", "Agente creado — entrega el código al PC");
    } catch (e: any) {
      flash("err", humanizeError(e, "No se pudo crear el agente"));
    } finally {
      setCreatingAgent(false);
    }
  };

  const handleDeleteAgent = async (id: number, name: string) => {
    if (!confirm(`¿Eliminar el agente "${name}"? El PC ya no podrá recibir trabajos.`)) return;
    try {
      await apiFetch(`/printing/agents/${id}/`, { method: "DELETE" });
      // Also clean up local printer configs that referenced this agent
      getSavedPrinters()
        .filter(p => p.type === "agent" && p.agentId === id)
        .forEach(p => removePrinter(p.id));
      await reloadAgents();
      reload();
      flash("ok", "Agente eliminado");
    } catch (e: any) {
      flash("err", humanizeError(e, "No se pudo eliminar"));
    }
  };

  const handleRegenCode = async (id: number, name: string) => {
    try {
      const resp = (await apiFetch(`/printing/agents/${id}/regenerate-code/`, {
        method: "POST",
      })) as { pairing_code: string; pairing_expires_at: string };
      setPairingInfo({
        agentId: id, name, code: resp.pairing_code, expires_at: resp.pairing_expires_at,
      });
      await reloadAgents();
    } catch (e: any) {
      flash("err", humanizeError(e, "No se pudo regenerar el código"));
    }
  };

  const handleAdoptPrinter = (agent: AgentDTO, p: AgentPrinterDTO) => {
    const cfg: PrinterConfig = {
      id: generateId(),
      name: `${agent.name} · ${p.display_name || p.name}`,
      type: "agent",
      paperWidth: (p.paper_width === 58 ? 58 : 80) as 58 | 80,
      agentId: agent.id,
      agentPrinterName: p.name,
    };
    savePrinter(cfg);
    reload();
    flash("ok", `"${p.display_name || p.name}" agregada como impresora`);
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      flash("ok", "Copiado al portapapeles");
    } catch {
      flash("err", "No se pudo copiar");
    }
  };

  // Detecta impresoras tipo "network" guardadas en localStorage que ya no
  // funcionan (el endpoint del servidor fue removido — ahora la red se hace
  // vía agente). Mostramos un aviso para que el usuario las migre.
  const legacyNetworkPrinters = printers.filter(p => p.type === "network");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      {/* Banner de bienvenida al modelo "PC del local" */}
      <div style={{
        background: C.accentBg, border: `1px solid ${C.accentBd}`, borderRadius: 10,
        padding: "12px 14px", fontSize: 12.5, color: C.accent, lineHeight: 1.55,
      }}>
        <div style={{ fontWeight: 800, marginBottom: 4 }}>🖨️ Cómo funciona la impresión en Pulstock</div>
        <div style={{ color: C.mid }}>
          Configura <strong>UN PC en el local</strong> con el Pulstock Printer Agent y conecta ahí
          tus impresoras (térmica de caja, comanda de cocina, etc.). Cuando cualquiera del staff
          aprieta &ldquo;Imprimir&rdquo; desde su celular o tablet, la comanda sale
          <strong> automáticamente en ese PC</strong>, sin tener que configurar nada en cada dispositivo.
        </div>
      </div>

      {legacyNetworkPrinters.length > 0 && (
        <div style={{
          background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: 10,
          padding: "12px 14px", fontSize: 12.5, color: "#92400E", lineHeight: 1.55,
        }}>
          <div style={{ fontWeight: 800, marginBottom: 4 }}>
            ⚠ Tienes {legacyNetworkPrinters.length} impresora(s) de red configurada(s) al modo viejo
          </div>
          <div>
            La impresión LAN directa desde el servidor fue removida porque no funcionaba en producción
            (el servidor cloud no llega a tu red local). Configura tu impresora de red dentro del{" "}
            <strong>agente PC del local</strong> (sección de abajo): el agente sí está en tu LAN y puede
            imprimirle directamente. Después elimina la impresora vieja de la lista.
          </div>
        </div>
      )}

      <Card>
        <SectionHeader icon="🖨️" title="Impresoras de este dispositivo" desc="Opcional. Solo si quieres imprimir directamente desde este celular/PC (USB o Bluetooth). Para el flujo normal, usa el agente PC de abajo." />

        {printers.length === 0 && !showAdd && (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>🖨️</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.mid, marginBottom: 4 }}>No hay impresoras locales</div>
            <div style={{ fontSize: 12, color: C.mute, marginBottom: 16 }}>
              Lo normal es no configurar impresoras acá — el flujo recomendado usa el agente del PC del local (más abajo).
            </div>
          </div>
        )}

        {printers.map(p => {
          const badge = TYPE_BADGES[p.type];
          const isDefault = p.id === defaultId;
          return (
            <div key={p.id} style={{
              // En mobile: info arriba, botones abajo en row con wrap.
              // En desktop: info y botones en la misma fila.
              display: "flex",
              flexDirection: mob ? "column" : "row",
              alignItems: mob ? "stretch" : "center",
              gap: mob ? 8 : 12,
              padding: "12px 14px",
              border: `1.5px solid ${isDefault ? C.accentBd : C.border}`,
              borderRadius: 10, marginBottom: 8,
              background: isDefault ? C.accentBg : "transparent",
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{p.name}</span>
                  <span style={{
                    padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 700,
                    color: badge.color, background: badge.bg, border: `1px solid ${badge.bd}`,
                  }}>{badge.label}</span>
                  {isDefault && (
                    <span style={{
                      padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 700,
                      color: C.amber, background: C.amberBg, border: `1px solid ${C.amberBd}`,
                    }}>Predeterminada</span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: C.mute }}>
                  {p.paperWidth}mm{p.address ? ` · ${p.address}` : ""}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: mob ? "flex-start" : "flex-end" }}>
                {!isDefault && (
                  <button onClick={() => handleSetDefault(p.id)} className="cfg-btn" style={{
                    padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                    border: `1px solid ${C.border}`, borderRadius: 6, background: C.surface, color: C.mid,
                  }}>Predeterminada</button>
                )}
                <button onClick={() => handleTest(p)} className="cfg-btn" style={{
                  padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${C.accentBd}`, borderRadius: 6, background: C.accentBg, color: C.accent,
                }}>Test</button>
                <button onClick={() => handleRemove(p.id)} className="cfg-btn" style={{
                  padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${C.redBd}`, borderRadius: 6, background: C.redBg, color: C.red,
                }}>Eliminar</button>
              </div>
            </div>
          );
        })}

        <Divider />

        {!showAdd ? (
          <Btn onClick={() => { setShowAdd(true); setAddType(null); setAddName(""); setAddAddress(""); }} variant="primary">
            + Agregar impresora
          </Btn>
        ) : (
          <div style={{ border: `1.5px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Agregar impresora</div>

            {!addType ? (
              <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr", gap: 8 }}>
                {/* OJO: ya NO ofrecemos "Red / WiFi" acá. Las impresoras de red
                    se configuran en el PC del local con el agente — buscar la
                    sección de Agentes PC más abajo. */}
                {([
                  { type: "system" as PrinterType, icon: "🖥️", label: "Sistema (Windows)", desc: "Usa impresoras instaladas en tu PC" },
                  { type: "usb" as PrinterType, icon: "🔌", label: "USB directa", desc: "Conexión directa ESC/POS por cable" },
                  { type: "bluetooth" as PrinterType, icon: "📶", label: "Bluetooth", desc: "Impresora inalámbrica BT" },
                ]).map(opt => (
                  <button key={opt.type} onClick={() => setAddType(opt.type)} className="cfg-btn" style={{
                    padding: 16, border: `1.5px solid ${C.border}`, borderRadius: 10,
                    background: C.surface, cursor: "pointer", textAlign: "center",
                  }}>
                    <div style={{ fontSize: 28, marginBottom: 6 }}>{opt.icon}</div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{opt.label}</div>
                    <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{opt.desc}</div>
                  </button>
                ))}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {addType === "system" && (
                  <div style={{ background: "#F5F3FF", border: "1px solid #DDD6FE", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#5B21B6", lineHeight: 1.5 }}>
                    <strong>¿Cómo funciona?</strong> Al imprimir, se abrirá el diálogo de Windows donde podrás elegir entre tus impresoras instaladas (ej: POST 801, Microsoft Print to PDF, etc.). Usa el nombre de tu impresora real para identificarla fácilmente.
                  </div>
                )}
                <div style={FL}>
                  <Label>Nombre</Label>
                  <input style={iS} value={addName} onChange={e => setAddName(e.target.value)}
                    placeholder={addType === "system" ? "Ej: POST 801" : addType === "usb" ? "Ej: Caja principal" : addType === "bluetooth" ? "Ej: Impresora bar" : "Ej: Cocina"} />
                  {addType === "system" && <Hint>Ponle el mismo nombre de tu impresora en Windows para identificarla</Hint>}
                </div>
                <div style={FL}>
                  <Label>Ancho de papel</Label>
                  <div style={{ display: "flex", gap: 8 }}>
                    {([58, 80] as const).map(w => (
                      <button key={w} onClick={() => setAddWidth(w)} className="cfg-btn" style={{
                        padding: "7px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                        border: `1.5px solid ${addWidth === w ? C.accent : C.border}`,
                        borderRadius: 8, background: addWidth === w ? C.accentBg : "transparent",
                        color: addWidth === w ? C.accent : C.mid,
                      }}>{w}mm</button>
                    ))}
                  </div>
                </div>
                {addType === "network" && (
                  <>
                    <div style={{ background: C.greenBg, border: `1px solid ${C.greenBd}`, borderRadius: 8, padding: "10px 14px", fontSize: 12, color: C.green, lineHeight: 1.5 }}>
                      <strong>✓ Funciona con cualquier dispositivo</strong> (iPhone, Android, PC, tablet). La impresora se conecta al WiFi de tu local y TODOS imprimen desde allí sin configuración individual.
                    </div>
                    <div style={FL}>
                      <Label req>Dirección IP : Puerto</Label>
                      <input style={iS} value={addAddress} onChange={e => setAddAddress(e.target.value)}
                        placeholder="192.168.1.100:9100" />
                      <Hint>
                        Puerto 9100 es el estándar ESC/POS (no lo cambies si no sabes).
                        Revisa la IP de tu impresora en su menú de red o imprime el reporte de configuración.
                      </Hint>
                    </div>
                    <Btn onClick={handleTestNetworkConnection} disabled={pairing || !addAddress.trim()} variant="secondary">
                      {pairing ? "Probando..." : "🔍 Probar conexión"}
                    </Btn>
                  </>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                  <Btn onClick={() => {
                    if (addType === "system") handleAddSystem();
                    else if (addType === "usb") handleAddUSB();
                    else if (addType === "bluetooth") handleAddBluetooth();
                    else handleAddNetwork();
                  }} disabled={pairing} variant="primary">
                    {pairing ? "Conectando..." : (addType === "network" || addType === "system") ? "Agregar" : "Conectar y agregar"}
                  </Btn>
                  <Btn onClick={() => { setShowAdd(false); setAddType(null); }} variant="secondary">
                    Cancelar
                  </Btn>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ═══════════ Agentes PC — FLUJO PRINCIPAL (modelo Fudo) ═══════════ */}
      <Card>
        <SectionHeader
          icon="💻"
          title="PC del local (recomendado)"
          desc="El flujo principal. Configura un PC del local con el agente y todos los celulares/tablets imprimirán allí automáticamente."
        />

        {loadingAgents && agents.length === 0 && (
          <div style={{ textAlign: "center", padding: 16 }}><Spinner /></div>
        )}

        {agentsLoadError && (
          <div style={{
            background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 8,
            padding: "10px 14px", fontSize: 12, color: C.red, marginBottom: 10,
          }}>
            ⚠ Error al cargar agentes: {agentsLoadError}
            <button onClick={reloadAgents} style={{
              marginLeft: 8, border: "none", background: "transparent", color: C.red,
              cursor: "pointer", fontSize: 12, fontWeight: 700, textDecoration: "underline", padding: 0,
            }}>Reintentar</button>
          </div>
        )}

        {!loadingAgents && !agentsLoadError && agents.length === 0 && !showAddAgent && (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>💻</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.mid, marginBottom: 4 }}>No hay agentes PC</div>
            <div style={{ fontSize: 12, color: C.mute, marginBottom: 8, maxWidth: 480, margin: "0 auto 8px" }}>
              Con un agente PC, cualquier celular o tablet puede mandar a imprimir a las impresoras conectadas a ese PC — incluso desde datos móviles.
            </div>
          </div>
        )}

        {agents.map(a => {
          const statusBadge = a.is_pairing_pending
            ? { label: "Esperando emparejado", color: C.amber, bg: C.amberBg, bd: C.amberBd }
            : a.is_online
              ? { label: "En línea", color: C.green, bg: C.greenBg, bd: C.greenBd }
              : { label: "Desconectado", color: C.red, bg: C.redBg, bd: C.redBd };
          return (
            <div key={a.id} style={{
              border: `1.5px solid ${C.border}`, borderRadius: 10, padding: 14, marginBottom: 10,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 14, fontWeight: 700 }}>{a.name}</span>
                <span style={{
                  padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 700,
                  color: statusBadge.color, background: statusBadge.bg, border: `1px solid ${statusBadge.bd}`,
                }}>{statusBadge.label}</span>
                {a.os_info && <span style={{ fontSize: 11, color: C.mute }}>{a.os_info}</span>}
                <span style={{ fontSize: 11, color: C.mute, marginLeft: "auto" }}>
                  Última señal: {fmtLastSeen(a.last_seen_at)}
                </span>
              </div>

              {a.is_pairing_pending && (
                <div style={{
                  background: C.amberBg, border: `1px solid ${C.amberBd}`, borderRadius: 8,
                  padding: "10px 14px", fontSize: 12, color: "#92400E", marginBottom: 10, lineHeight: 1.5,
                }}>
                  Este agente aún no se ha conectado. Abre el software en el PC y escribe el código de emparejado.{" "}
                  <button onClick={() => handleRegenCode(a.id, a.name)} style={{
                    border: "none", background: "transparent", color: C.accent,
                    cursor: "pointer", fontSize: 12, fontWeight: 700, textDecoration: "underline", padding: 0,
                  }}>Generar un código nuevo</button>
                </div>
              )}

              {a.printers.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: C.mid, marginBottom: 6 }}>
                    Impresoras detectadas ({a.printers.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {a.printers.map(p => {
                      const savedList = printers;
                      const alreadyAdopted = savedList.some(
                        sp => sp.type === "agent" && sp.agentId === a.id && sp.agentPrinterName === p.name,
                      );
                      return (
                        <div key={p.id} style={{
                          display: "flex", alignItems: "center", gap: 8,
                          padding: "8px 10px", border: `1px solid ${C.border}`, borderRadius: 8,
                          background: C.surface,
                        }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {p.display_name || p.name}
                              {p.is_default && (
                                <span style={{
                                  marginLeft: 6, padding: "1px 6px", borderRadius: 99, fontSize: 9, fontWeight: 700,
                                  color: C.amber, background: C.amberBg, border: `1px solid ${C.amberBd}`,
                                }}>Default PC</span>
                              )}
                            </div>
                            <div style={{ fontSize: 11, color: C.mute }}>
                              {p.connection_type} · {p.paper_width}mm
                              {p.network_address ? ` · ${p.network_address}` : ""}
                            </div>
                          </div>
                          <button
                            onClick={() => handleAdoptPrinter(a, p)}
                            disabled={alreadyAdopted}
                            className="cfg-btn"
                            style={{
                              padding: "5px 10px", fontSize: 11, fontWeight: 600,
                              cursor: alreadyAdopted ? "default" : "pointer",
                              border: `1px solid ${alreadyAdopted ? C.border : C.accentBd}`,
                              borderRadius: 6,
                              background: alreadyAdopted ? C.surface : C.accentBg,
                              color: alreadyAdopted ? C.mute : C.accent,
                              opacity: alreadyAdopted ? 0.6 : 1,
                            }}>
                            {alreadyAdopted ? "Ya agregada" : "Usar aquí"}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {!a.is_pairing_pending && a.printers.length === 0 && (
                <div style={{ fontSize: 12, color: C.mute, marginBottom: 10, fontStyle: "italic" }}>
                  El agente aún no ha reportado impresoras. Asegúrate de tener impresoras instaladas en el PC y reinicia el agente.
                </div>
              )}

              <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                <button onClick={() => handleDeleteAgent(a.id, a.name)} className="cfg-btn" style={{
                  padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${C.redBd}`, borderRadius: 6, background: C.redBg, color: C.red,
                }}>Eliminar agente</button>
              </div>
            </div>
          );
        })}

        <Divider />

        {!showAddAgent ? (
          <Btn onClick={() => { setShowAddAgent(true); setNewAgentName(""); }} variant="primary">
            + Agregar agente PC
          </Btn>
        ) : (
          <div style={{ border: `1.5px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Nuevo agente PC</div>
            <div style={{ background: C.accentBg, border: `1px solid ${C.accentBd}`, borderRadius: 8, padding: "10px 14px", fontSize: 12, color: C.accent, lineHeight: 1.5, marginBottom: 12 }}>
              <strong>¿Cómo funciona?</strong> Crearemos un código que vas a ingresar en el software que se instala en el PC del local. Una vez emparejado, cualquier celular o tablet podrá mandar a imprimir allí.
            </div>
            <div style={FL}>
              <Label req>Nombre del PC</Label>
              <input style={iS} value={newAgentName} onChange={e => setNewAgentName(e.target.value)}
                placeholder="Ej: PC Caja Principal" />
              <Hint>Un nombre descriptivo para identificar este PC en la lista.</Hint>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <Btn onClick={handleCreateAgent} disabled={creatingAgent || !newAgentName.trim()} variant="primary">
                {creatingAgent ? "Creando..." : "Crear y generar código"}
              </Btn>
              <Btn onClick={() => { setShowAddAgent(false); setNewAgentName(""); }} variant="secondary">
                Cancelar
              </Btn>
            </div>
          </div>
        )}
      </Card>

      {/* ═══════════ Pairing code modal ═══════════ */}
      {pairingInfo && (
        <div onClick={() => setPairingInfo(null)} style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
          zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: C.surface, borderRadius: 12, maxWidth: 520, width: "100%",
            padding: 24, boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
          }}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 4 }}>
              Empareja el PC "{pairingInfo.name}"
            </div>
            <div style={{ fontSize: 13, color: C.mute, marginBottom: 16 }}>
              Instala <strong>Pulstock Printer Agent</strong> en el PC y escribe este código cuando lo pida:
            </div>

            <div style={{
              background: C.accentBg, border: `2px dashed ${C.accentBd}`, borderRadius: 10,
              padding: "20px 16px", textAlign: "center", marginBottom: 12,
            }}>
              <div style={{ fontSize: 11, color: C.mute, marginBottom: 6, letterSpacing: 1 }}>CÓDIGO</div>
              <div style={{
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                fontSize: 32, fontWeight: 900, letterSpacing: 4, color: C.accent,
              }}>
                {pairingInfo.code}
              </div>
              <button onClick={() => copyToClipboard(pairingInfo.code)} className="cfg-btn" style={{
                marginTop: 10, padding: "5px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                border: `1px solid ${C.accentBd}`, borderRadius: 6, background: C.surface, color: C.accent,
              }}>📋 Copiar</button>
            </div>

            <div style={{ fontSize: 12, color: C.mute, marginBottom: 16, lineHeight: 1.6 }}>
              <div style={{ marginBottom: 4 }}><strong>Pasos:</strong></div>
              <ol style={{ paddingLeft: 20, margin: 0 }}>
                <li>En el PC, descarga el instalador desde <span style={{ fontFamily: "monospace", color: C.accent }}>pulstock.cl/agent</span></li>
                <li>Ejecuta el instalador</li>
                <li>Cuando te pida el código, escribe: <strong>{pairingInfo.code}</strong></li>
                <li>El PC aparecerá como "En línea" en esta página</li>
              </ol>
              <div style={{ marginTop: 8, color: C.amber }}>
                {(() => {
                  try {
                    const mins = Math.max(1, Math.round(
                      (new Date(pairingInfo.expires_at).getTime() - Date.now()) / 60000
                    ));
                    return `⚠ El código expira en ${mins} minutos. Si expira, puedes regenerar uno nuevo.`;
                  } catch {
                    return "⚠ El código expira pronto. Si expira, puedes regenerar uno nuevo.";
                  }
                })()}
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <Btn onClick={() => setPairingInfo(null)} variant="primary">
                Listo
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
