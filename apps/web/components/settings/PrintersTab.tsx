"use client";
import { useEffect, useState } from "react";
import { C } from "@/lib/theme";
import type { PrinterConfig, PrinterType } from "@/lib/printer";
import { Card, SectionHeader, Divider, Btn, Spinner, Label, Hint, iS, FL } from "./SettingsUI";

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
      const { getSavedPrinters, getDefaultPrinter } = require("@/lib/printer");
      setPrinters(getSavedPrinters());
      setDefaultId(getDefaultPrinter()?.id || null);
    } catch { setPrinters([]); }
  };

  useEffect(() => { reload(); }, []);

  const handleRemove = (id: string) => {
    if (!confirm("¿Eliminar esta impresora?")) return;
    const { removePrinter } = require("@/lib/printer");
    removePrinter(id);
    reload();
    flash("ok", "Impresora eliminada");
  };

  const handleSetDefault = (id: string) => {
    const { setDefaultPrinter } = require("@/lib/printer");
    setDefaultPrinter(id);
    setDefaultId(id);
    flash("ok", "Impresora predeterminada actualizada");
  };

  const handleTest = async (p: PrinterConfig) => {
    try {
      if (p.type === "system") {
        const { printSystemReceipt } = require("@/lib/printer");
        const html = `
          <div class="title">PRUEBA</div>
          <div class="sep-double"></div>
          <div class="row"><span>Impresora:</span><span>${p.name}</span></div>
          <div class="row"><span>Tipo:</span><span>${p.type.toUpperCase()}</span></div>
          <div class="row"><span>Ancho:</span><span>${p.paperWidth}mm</span></div>
          <div class="sep-double"></div>
          <div class="center">Impresión OK!</div>
        `;
        printSystemReceipt(html, p);
        flash("ok", "Prueba enviada al diálogo de impresión");
      } else {
        const { EscPos } = require("@/lib/escpos");
        const { printBytes } = require("@/lib/printer");
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
      flash("err", e?.message || "Error al imprimir prueba");
    }
  };

  const handleAddUSB = async () => {
    setPairing(true);
    try {
      const { pairUSBPrinter, savePrinter, generateId } = require("@/lib/printer");
      await pairUSBPrinter();
      const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora USB", type: "usb", paperWidth: addWidth };
      savePrinter(cfg);
      reload();
      setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
      flash("ok", "Impresora USB agregada");
    } catch (e: any) {
      flash("err", e?.message || "No se pudo conectar la impresora USB");
    } finally { setPairing(false); }
  };

  const handleAddBluetooth = async () => {
    setPairing(true);
    try {
      const { pairBluetoothPrinter, savePrinter, generateId } = require("@/lib/printer");
      await pairBluetoothPrinter();
      const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora Bluetooth", type: "bluetooth", paperWidth: addWidth };
      savePrinter(cfg);
      reload();
      setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
      flash("ok", "Impresora Bluetooth agregada");
    } catch (e: any) {
      flash("err", e?.message || "No se pudo conectar la impresora Bluetooth");
    } finally { setPairing(false); }
  };

  const handleAddNetwork = () => {
    if (!addAddress.trim()) { flash("err", "Ingresa la dirección IP"); return; }
    const { savePrinter, generateId } = require("@/lib/printer");
    const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora Red", type: "network", paperWidth: addWidth, address: addAddress.trim() };
    savePrinter(cfg);
    reload();
    setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
    flash("ok", "Impresora de red agregada");
  };

  const handleAddSystem = () => {
    const { savePrinter, generateId } = require("@/lib/printer");
    const cfg: PrinterConfig = { id: generateId(), name: addName || "Impresora del sistema", type: "system", paperWidth: addWidth };
    savePrinter(cfg);
    reload();
    setShowAdd(false); setAddType(null); setAddName(""); setAddAddress("");
    flash("ok", "Impresora del sistema agregada");
  };

  const TYPE_BADGES: Record<PrinterType, { label: string; color: string; bg: string; bd: string }> = {
    usb: { label: "USB", color: C.accent, bg: C.accentBg, bd: C.accentBd },
    bluetooth: { label: "Bluetooth", color: "#2563EB", bg: "#EFF6FF", bd: "#BFDBFE" },
    network: { label: "Red/WiFi", color: C.green, bg: C.greenBg, bd: C.greenBd },
    system: { label: "Sistema", color: "#7C3AED", bg: "#F5F3FF", bd: "#DDD6FE" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Card>
        <SectionHeader icon="🖨️" title="Impresoras térmicas" desc="Configura tus impresoras para imprimir boletas y pre-cuentas directamente" />

        {printers.length === 0 && !showAdd && (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>🖨️</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.mid, marginBottom: 4 }}>No hay impresoras configuradas</div>
            <div style={{ fontSize: 12, color: C.mute, marginBottom: 16 }}>Agrega una impresora térmica para imprimir boletas y pre-cuentas</div>
          </div>
        )}

        {printers.map(p => {
          const badge = TYPE_BADGES[p.type];
          const isDefault = p.id === defaultId;
          return (
            <div key={p.id} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
              border: `1.5px solid ${isDefault ? C.accentBd : C.border}`,
              borderRadius: 10, marginBottom: 8,
              background: isDefault ? C.accentBg : "transparent",
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
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
              <div style={{ display: "flex", gap: 6 }}>
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
          <Btn onClick={() => { setShowAdd(true); setAddType(null); setAddName(""); setAddAddress(""); }} color={C.accent}>
            + Agregar impresora
          </Btn>
        ) : (
          <div style={{ border: `1.5px solid ${C.border}`, borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Agregar impresora</div>

            {!addType ? (
              <div style={{ display: "grid", gridTemplateColumns: mob ? "1fr" : "1fr 1fr", gap: 8 }}>
                {([
                  { type: "system" as PrinterType, icon: "🖥️", label: "Sistema (Windows)", desc: "Usa impresoras instaladas en tu PC" },
                  { type: "usb" as PrinterType, icon: "🔌", label: "USB directa", desc: "Conexión directa ESC/POS por cable" },
                  { type: "bluetooth" as PrinterType, icon: "📶", label: "Bluetooth", desc: "Impresora inalámbrica BT" },
                  { type: "network" as PrinterType, icon: "🌐", label: "Red / WiFi", desc: "Conexión por IP de red" },
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
                  <div style={FL}>
                    <Label req>Dirección IP</Label>
                    <input style={iS} value={addAddress} onChange={e => setAddAddress(e.target.value)}
                      placeholder="192.168.1.100:9100" />
                    <Hint>IP y puerto de la impresora en tu red local</Hint>
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                  <Btn onClick={() => {
                    if (addType === "system") handleAddSystem();
                    else if (addType === "usb") handleAddUSB();
                    else if (addType === "bluetooth") handleAddBluetooth();
                    else handleAddNetwork();
                  }} disabled={pairing}>
                    {pairing ? "Conectando..." : (addType === "network" || addType === "system") ? "Agregar" : "Conectar y agregar"}
                  </Btn>
                  <Btn onClick={() => { setShowAdd(false); setAddType(null); }} variant="outline" color={C.mid}>
                    Cancelar
                  </Btn>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
