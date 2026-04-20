/**
 * Printer service — manages printer config (localStorage) and dispatches
 * ESC/POS byte arrays to USB, Bluetooth, network, or window.print fallback.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

// WebUSB / Web Bluetooth types (not in default TS lib)
declare global {
  interface Navigator {
    usb?: any;
    bluetooth?: any;
  }
}

// ── Types ────────────────────────────────────────────────────────────────────

export type PrinterType = "usb" | "bluetooth" | "network" | "system" | "agent";

export interface PrinterConfig {
  id: string;
  name: string;
  type: PrinterType;
  paperWidth: 58 | 80;
  address?: string; // IP:port for network printers
  // For type === "agent": identifica el agente PC y la impresora dentro del agente
  agentId?: number;
  agentPrinterName?: string;
}

// ── localStorage keys ────────────────────────────────────────────────────────

const PRINTERS_KEY = "pulstock_printers";
const DEFAULT_KEY = "pulstock_default_printer";

// ── Config CRUD ──────────────────────────────────────────────────────────────

export function getSavedPrinters(): PrinterConfig[] {
  try {
    return JSON.parse(localStorage.getItem(PRINTERS_KEY) || "[]");
  } catch {
    return [];
  }
}

export function savePrinter(p: PrinterConfig): void {
  const list = getSavedPrinters();
  const idx = list.findIndex((x) => x.id === p.id);
  if (idx >= 0) list[idx] = p;
  else list.push(p);
  localStorage.setItem(PRINTERS_KEY, JSON.stringify(list));
}

export function removePrinter(id: string): void {
  const list = getSavedPrinters().filter((p) => p.id !== id);
  localStorage.setItem(PRINTERS_KEY, JSON.stringify(list));
  if (localStorage.getItem(DEFAULT_KEY) === id) {
    localStorage.removeItem(DEFAULT_KEY);
  }
}

export function getDefaultPrinter(): PrinterConfig | null {
  const id = localStorage.getItem(DEFAULT_KEY);
  if (!id) {
    const list = getSavedPrinters();
    return list.length === 1 ? list[0] : null;
  }
  return getSavedPrinters().find((p) => p.id === id) || null;
}

export function setDefaultPrinter(id: string): void {
  localStorage.setItem(DEFAULT_KEY, id);
}

export function generateId(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

// ── WebUSB ───────────────────────────────────────────────────────────────────

let cachedUSBDevice: any = null;

export async function pairUSBPrinter(): Promise<any> {
  if (!navigator.usb) throw new Error("WebUSB no disponible en este navegador");
  const device = await navigator.usb.requestDevice({
    filters: [{ classCode: 7 }], // Printer class
  });
  cachedUSBDevice = device;
  return device;
}

async function sendUSB(data: Uint8Array): Promise<void> {
  if (!navigator.usb) throw new Error("WebUSB no disponible");

  let device = cachedUSBDevice;

  // Try to get previously paired devices
  if (!device) {
    const devices = await navigator.usb.getDevices();
    device = devices.find((d: any) => d.configuration?.interfaces.some(
      (i: any) => i.alternate.interfaceClass === 7
    )) || null;
  }

  if (!device) {
    device = await navigator.usb.requestDevice({ filters: [{ classCode: 7 }] });
  }

  cachedUSBDevice = device;

  await device.open();
  if (device.configuration === null) {
    await device.selectConfiguration(1);
  }

  // Find printer interface and endpoint
  const iface = device.configuration!.interfaces.find(
    (i: any) => i.alternate.interfaceClass === 7
  );
  if (!iface) throw new Error("No se encontró interfaz de impresora");

  await device.claimInterface(iface.interfaceNumber);

  const ep = iface.alternate.endpoints.find((e: any) => e.direction === "out");
  if (!ep) throw new Error("No se encontró endpoint de salida");

  await device.transferOut(ep.endpointNumber, data);
}

// ── Web Bluetooth ────────────────────────────────────────────────────────────

const BT_SERVICES = [
  "000018f0-0000-1000-8000-00805f9b34fb", // common thermal printer service
  "e7810a71-73ae-499d-8c15-faa9aef0c3f2", // another common service
  "0000fff0-0000-1000-8000-00805f9b34fb", // ESC/POS generic
];

let cachedBTDevice: any = null;
let cachedBTCharacteristic: any = null;

export async function pairBluetoothPrinter(): Promise<any> {
  if (!navigator.bluetooth) throw new Error("Web Bluetooth no disponible en este navegador");
  const device = await navigator.bluetooth.requestDevice({
    acceptAllDevices: true,
    optionalServices: BT_SERVICES,
  });
  cachedBTDevice = device;
  cachedBTCharacteristic = null;
  return device;
}

async function connectAndFindCharacteristic(device: any): Promise<any> {
  const server = await device.gatt!.connect();
  const services = await server.getPrimaryServices();
  for (const svc of services) {
    const chars = await svc.getCharacteristics();
    for (const ch of chars) {
      if (ch.properties.write || ch.properties.writeWithoutResponse) {
        return ch;
      }
    }
  }
  throw new Error("No se encontró característica de escritura en la impresora Bluetooth");
}

async function sendBluetooth(data: Uint8Array): Promise<void> {
  if (!navigator.bluetooth) throw new Error("Web Bluetooth no disponible");

  // 1. Try cached characteristic
  if (cachedBTCharacteristic) {
    try {
      await sendBTChunks(cachedBTCharacteristic, data);
      return;
    } catch {
      cachedBTCharacteristic = null;
    }
  }

  // 2. Try reconnecting cached device (no user prompt)
  if (cachedBTDevice?.gatt) {
    try {
      const ch = await connectAndFindCharacteristic(cachedBTDevice);
      cachedBTCharacteristic = ch;
      await sendBTChunks(ch, data);
      return;
    } catch {
      cachedBTDevice = null;
      cachedBTCharacteristic = null;
    }
  }

  // 3. Request new device (shows browser picker)
  const device = await navigator.bluetooth.requestDevice({
    acceptAllDevices: true,
    optionalServices: BT_SERVICES,
  });

  cachedBTDevice = device;
  const ch = await connectAndFindCharacteristic(device);
  cachedBTCharacteristic = ch;
  await sendBTChunks(ch, data);
}

async function sendBTChunks(ch: any, data: Uint8Array): Promise<void> {
  const CHUNK = 20; // standard BLE MTU — safer for all printers
  for (let i = 0; i < data.length; i += CHUNK) {
    const chunk = data.slice(i, i + CHUNK);
    if (ch.properties.writeWithoutResponse) {
      await ch.writeValueWithoutResponse(chunk);
    } else {
      await ch.writeValueWithResponse(chunk);
    }
    // Small delay between chunks for stable BLE transmission
    if (i + CHUNK < data.length) {
      await new Promise(r => setTimeout(r, 10));
    }
  }
}

// ── Network ──────────────────────────────────────────────────────────────────

/**
 * Parse "192.168.1.50:9100" → { host, port }
 * Defaults to port 9100 (standard ESC/POS).
 */
function parseNetworkAddress(address: string): { host: string; port: number } {
  const clean = address.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  const [host, portStr] = clean.split(":");
  const port = portStr ? parseInt(portStr, 10) : 9100;
  return { host: host.trim(), port: Number.isFinite(port) ? port : 9100 };
}

/**
 * Send ESC/POS bytes to a network printer (LAN).
 *
 * Browsers cannot open raw TCP sockets, so this POSTs to our backend proxy
 * (/api/core/print/network/) which opens the TCP connection on port 9100
 * (or whatever is specified) and forwards the ESC/POS data.
 *
 * The backend validates the target IP is in a private LAN range (anti-SSRF).
 */
async function sendNetwork(data: Uint8Array, address: string): Promise<void> {
  const { host, port } = parseNetworkAddress(address);

  // Convert bytes to base64 for JSON transport
  let binary = "";
  for (let i = 0; i < data.byteLength; i++) {
    binary += String.fromCharCode(data[i]);
  }
  const data_b64 = btoa(binary);

  // Import dynamically to avoid circular deps
  const { apiFetch } = await import("@/lib/api");
  await apiFetch("/core/print/network/", {
    method: "POST",
    body: JSON.stringify({ host, port, data_b64 }),
  });
}

/**
 * Test connectivity to a network printer (without actually printing).
 * Sends a minimal ESC/POS beep/feed command.
 */
export async function testNetworkPrinter(address: string): Promise<{ ok: boolean; error?: string }> {
  try {
    // ESC @ (initialize) + LF (feed) — totally harmless
    const testBytes = new Uint8Array([0x1b, 0x40, 0x0a]);
    await sendNetwork(testBytes, address);
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: e?.message || String(e) };
  }
}

// ── Agent PC (cloud-pull) ────────────────────────────────────────────────────

/**
 * Queue a print job on an agent PC via the Pulstock API.
 * The agent polls the API and will pick up the job within ~3 seconds.
 *
 * Works from any device (celular con datos, tablet en otra red, etc) —
 * la única condición es que el PC con el agente tenga internet.
 */
async function sendAgent(data: Uint8Array, printer: PrinterConfig): Promise<void> {
  if (!printer.agentId) {
    throw new Error("Agente no configurado en la impresora");
  }

  // Convert bytes to base64
  let binary = "";
  for (let i = 0; i < data.byteLength; i++) {
    binary += String.fromCharCode(data[i]);
  }
  const data_b64 = btoa(binary);

  const { apiFetch, ApiError } = await import("@/lib/api");
  try {
    await apiFetch("/printing/jobs/queue/", {
      method: "POST",
      body: JSON.stringify({
        agent_id: printer.agentId,
        printer_name: printer.agentPrinterName || "",
        data_b64,
        source: "web",
      }),
    });
  } catch (e: any) {
    // Mensajes específicos para ayudar al usuario a diagnosticar
    if (e instanceof ApiError) {
      if (e.status === 404) {
        throw new Error("Agente no encontrado. Puede que lo hayan eliminado — quita esta impresora y vuelve a agregarla.");
      }
      if (e.status === 402) {
        throw new Error("Suscripción no activa — renueva tu plan para imprimir.");
      }
      if (e.status === 400) {
        throw new Error("Datos del trabajo de impresión inválidos.");
      }
    }
    throw e;
  }
}

// ── Main print function ──────────────────────────────────────────────────────

export async function printBytes(data: Uint8Array, printer?: PrinterConfig | null): Promise<void> {
  const p = printer || getDefaultPrinter();

  if (!p) {
    throw new Error("No hay impresora configurada");
  }

  switch (p.type) {
    case "usb":
      await sendUSB(data);
      break;
    case "bluetooth":
      await sendBluetooth(data);
      break;
    case "network":
      if (!p.address) throw new Error("Dirección de red no configurada");
      await sendNetwork(data, p.address);
      break;
    case "agent":
      await sendAgent(data, p);
      break;
    case "system":
      // System printers can't receive raw bytes — caller should use printSystemReceipt instead
      throw new Error("Usa printSystemReceipt para impresoras del sistema");
    default:
      throw new Error(`Tipo de impresora desconocido: ${(p as any).type}`);
  }
}

/** Print HTML via the OS print dialog (for "system" type printers). */
export function printSystemReceipt(html: string, printer?: PrinterConfig | null): void {
  const p = printer || getDefaultPrinter();
  printHTML(html, p?.paperWidth ?? 80);
}

// ── Universal print orchestrator ─────────────────────────────────────────────

export interface UniversalPrintInput {
  /** Raw ESC/POS bytes (for thermal printers). Optional if only html provided. */
  bytes?: Uint8Array;
  /** HTML receipt (for system dialog fallback). Always required. */
  html: string;
  /** Preferred paper width for HTML fallback. */
  paperWidth?: 58 | 80;
}

/**
 * Imprime usando el método más universal disponible.
 *
 * Intenta en orden:
 *   1. La impresora por defecto (BLE/USB/Network), si está configurada
 *   2. Cae a window.print() (AirPrint/Google Cloud Print/cualquier impresora del sistema)
 *
 * SIEMPRE termina imprimiendo (mediante el diálogo del navegador) si todo lo demás falla.
 */
export async function printUniversal(input: UniversalPrintInput): Promise<{ method: string; ok: boolean; error?: string }> {
  const p = getDefaultPrinter();
  const width: 58 | 80 = input.paperWidth || p?.paperWidth || 80;

  // If no default printer → straight to system dialog
  if (!p || p.type === "system") {
    try {
      printHTML(input.html, width);
      return { method: "system", ok: true };
    } catch (e: any) {
      return { method: "system", ok: false, error: e?.message || "Error al imprimir" };
    }
  }

  // If we have bytes, try the configured printer
  if (input.bytes) {
    try {
      await printBytes(input.bytes, p);
      return { method: p.type, ok: true };
    } catch (e: any) {
      // Fall through to system dialog
      const err = e?.message || String(e);
      try {
        printHTML(input.html, width);
        return { method: "system", ok: true, error: `Fallback desde ${p.type}: ${err}` };
      } catch (e2: any) {
        return { method: "failed", ok: false, error: `${p.type} falló: ${err}. Diálogo tampoco funcionó: ${e2?.message}` };
      }
    }
  }

  // No bytes available → go straight to system dialog
  try {
    printHTML(input.html, width);
    return { method: "system", ok: true };
  } catch (e: any) {
    return { method: "system", ok: false, error: e?.message || "Error al imprimir" };
  }
}

// ── HTML fallback (window.print) ─────────────────────────────────────────────

export function printHTML(html: string, paperWidth: 58 | 80 = 80): void {
  // Inner body width with margins for thermal printers (safe-zone)
  const bodyW = paperWidth === 58 ? "48mm" : "72mm";
  const pageW = `${paperWidth}mm`;

  const CSS = `
    /* ─── Thermal printer page settings ───────────────────────── */
    @page {
      margin: 0;
      size: ${pageW} auto;
    }
    @media print {
      @page {
        margin: 0 !important;
        size: ${pageW} auto !important;
      }
      html, body {
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
        color-adjust: exact !important;
      }
      /* Hide anything that shouldn't print */
      .no-print { display: none !important; }
    }

    /* ─── Reset ───────────────────────────────────────────────── */
    * { box-sizing: border-box; margin: 0; padding: 0; }

    /* ─── Base body ───────────────────────────────────────────── */
    html, body {
      width: ${bodyW};
      margin: 0 auto;
      padding: 3mm 2mm;
      background: #fff;
    }
    body {
      font-family: 'Courier New', 'Lucida Console', 'Consolas', monospace;
      font-size: 11px;
      line-height: 1.4;
      color: #000;
      /* Improve font rendering for thermal */
      -webkit-font-smoothing: none;
      -moz-osx-font-smoothing: none;
      text-rendering: optimizeLegibility;
      /* Prevent text from being cut off */
      word-wrap: break-word;
      overflow-wrap: break-word;
    }

    /* ─── Receipt elements ────────────────────────────────────── */
    .title {
      text-align: center;
      font-size: ${paperWidth === 58 ? "14px" : "16px"};
      font-weight: 900;
      letter-spacing: 1px;
      padding: 4px 0;
    }
    .center { text-align: center; }
    .right  { text-align: right; }
    .left   { text-align: left; }
    .bold   { font-weight: bold; }
    .big    { font-size: ${paperWidth === 58 ? "13px" : "15px"}; }
    .small  { font-size: ${paperWidth === 58 ? "9px" : "10px"}; }

    /* ─── Separators ──────────────────────────────────────────── */
    .sep {
      border-top: 1px dashed #000;
      margin: 5px 0;
    }
    .sep-double {
      border-top: 2px solid #000;
      margin: 5px 0;
    }
    .sep-thick {
      border-top: 3px solid #000;
      margin: 6px 0;
    }

    /* ─── Rows (item name + price) ────────────────────────────── */
    .row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 1px 0;
      gap: 4px;
    }
    .row .price {
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      flex-shrink: 0;
    }
    .item-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
      min-width: 0;
      padding-right: 8px;
    }

    /* ─── Information blocks ──────────────────────────────────── */
    .info   { font-size: 10px; color: #333; }
    .total-row {
      font-size: ${paperWidth === 58 ? "13px" : "14px"};
      font-weight: 900;
      padding: 3px 0;
    }
    .disclaimer {
      font-size: 9px;
      text-align: center;
      padding: 6px 0 2px;
      color: #555;
    }
    .footer {
      text-align: center;
      font-size: 10px;
      padding-top: 6px;
      color: #555;
    }

    /* ─── Barcode / QR placeholder ────────────────────────────── */
    .barcode {
      text-align: center;
      font-family: 'Libre Barcode 128', monospace;
      font-size: 24px;
      letter-spacing: 1px;
      margin: 4px 0;
    }
    .qr {
      text-align: center;
      margin: 6px auto;
    }
    .qr img {
      max-width: 30mm;
      height: auto;
      display: inline-block;
    }
  `;

  // Use hidden iframe to print without opening a new window
  const id = "pulstock-print-frame";
  let iframe = document.getElementById(id) as HTMLIFrameElement | null;
  if (iframe) iframe.remove();

  iframe = document.createElement("iframe");
  iframe.id = id;
  iframe.setAttribute("aria-hidden", "true");
  iframe.style.cssText = `
    position:fixed;left:-9999px;top:-9999px;
    width:${paperWidth}mm;height:0;border:none;
    visibility:hidden;
  `;
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument || iframe.contentWindow?.document;
  if (!doc) return;

  doc.open();
  doc.write(`<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Boleta Pulstock</title>
  <style>${CSS}</style>
</head>
<body>${html}</body>
</html>`);
  doc.close();

  // Wait for fonts/content to load, then trigger print
  const doPrint = () => {
    try {
      iframe!.contentWindow?.focus();
      iframe!.contentWindow?.print();
    } catch (e) {
      // Silently ignore — user may have cancelled
    } finally {
      // Cleanup after print dialog closes
      setTimeout(() => iframe?.remove(), 3000);
    }
  };

  // Give the browser time to render fonts + layout
  if (iframe.contentDocument?.readyState === "complete") {
    setTimeout(doPrint, 150);
  } else {
    iframe.addEventListener("load", () => setTimeout(doPrint, 150), { once: true });
    // Fallback if load never fires
    setTimeout(doPrint, 500);
  }
}
