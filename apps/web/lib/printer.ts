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

export type PrinterType = "usb" | "bluetooth" | "network" | "system";

export interface PrinterConfig {
  id: string;
  name: string;
  type: PrinterType;
  paperWidth: 58 | 80;
  address?: string; // IP:port for network printers
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

let cachedBTCharacteristic: any = null;

export async function pairBluetoothPrinter(): Promise<any> {
  if (!navigator.bluetooth) throw new Error("Web Bluetooth no disponible en este navegador");
  const device = await navigator.bluetooth.requestDevice({
    acceptAllDevices: true,
    optionalServices: [
      "000018f0-0000-1000-8000-00805f9b34fb", // common thermal printer service
      "e7810a71-73ae-499d-8c15-faa9aef0c3f2", // another common service
    ],
  });
  return device;
}

async function sendBluetooth(data: Uint8Array): Promise<void> {
  if (!navigator.bluetooth) throw new Error("Web Bluetooth no disponible");

  // Try cached characteristic first
  if (cachedBTCharacteristic) {
    try {
      // BLE has 20-byte MTU typical, send in chunks
      await sendBTChunks(cachedBTCharacteristic, data);
      return;
    } catch {
      cachedBTCharacteristic = null;
    }
  }

  const device = await navigator.bluetooth.requestDevice({
    acceptAllDevices: true,
    optionalServices: [
      "000018f0-0000-1000-8000-00805f9b34fb",
      "e7810a71-73ae-499d-8c15-faa9aef0c3f2",
    ],
  });

  const server = await device.gatt!.connect();
  const services = await server.getPrimaryServices();

  // Find writable characteristic
  for (const svc of services) {
    const chars = await svc.getCharacteristics();
    for (const ch of chars) {
      if (ch.properties.write || ch.properties.writeWithoutResponse) {
        cachedBTCharacteristic = ch;
        await sendBTChunks(ch, data);
        return;
      }
    }
  }

  throw new Error("No se encontró característica de escritura en la impresora Bluetooth");
}

async function sendBTChunks(ch: any, data: Uint8Array): Promise<void> {
  const CHUNK = 100; // safe chunk size for BLE
  for (let i = 0; i < data.length; i += CHUNK) {
    const chunk = data.slice(i, i + CHUNK);
    if (ch.properties.writeWithoutResponse) {
      await ch.writeValueWithoutResponse(chunk);
    } else {
      await ch.writeValueWithResponse(chunk);
    }
  }
}

// ── Network ──────────────────────────────────────────────────────────────────

async function sendNetwork(data: Uint8Array, address: string): Promise<void> {
  // Try HTTP POST — works with some modern thermal printers
  // and with print server proxies
  const url = address.startsWith("http") ? address : `http://${address}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: data as any,
  });
  if (!res.ok) throw new Error(`Error de red: ${res.status}`);
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

// ── HTML fallback (window.print) ─────────────────────────────────────────────

export function printHTML(html: string, paperWidth: 58 | 80 = 80): void {
  const bodyW = paperWidth === 58 ? "48mm" : "72mm";
  const pageW = `${paperWidth}mm`;

  const CSS = `
    @page { margin: 0; size: ${pageW} auto; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { width: ${bodyW}; margin: 0 auto; padding: 3mm 2mm; }
    body {
      font-family: 'Courier New', 'Lucida Console', monospace;
      font-size: 11px; line-height: 1.4; color: #000;
    }
    .title { text-align: center; font-size: 16px; font-weight: 900; letter-spacing: 1px; padding: 4px 0; }
    .center { text-align: center; }
    .bold { font-weight: bold; }
    .sep { border-top: 1px dashed #000; margin: 5px 0; }
    .sep-double { border-top: 2px solid #000; margin: 5px 0; }
    .row { display: flex; justify-content: space-between; align-items: baseline; padding: 1px 0; }
    .row .price { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
    .info { font-size: 10px; color: #333; }
    .total-row { font-size: 14px; font-weight: 900; padding: 3px 0; }
    .disclaimer { font-size: 9px; text-align: center; padding: 6px 0 2px; color: #555; }
    .item-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; padding-right: 8px; }
    .footer { text-align: center; font-size: 10px; padding-top: 6px; color: #555; }
  `;

  // Use hidden iframe to print without opening a new window
  const id = "pulstock-print-frame";
  let iframe = document.getElementById(id) as HTMLIFrameElement | null;
  if (iframe) iframe.remove();

  iframe = document.createElement("iframe");
  iframe.id = id;
  iframe.style.cssText = "position:fixed;left:-9999px;top:-9999px;width:80mm;height:0;border:none;";
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument || iframe.contentWindow?.document;
  if (!doc) return;

  doc.open();
  doc.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Boleta</title><style>${CSS}</style></head><body>${html}</body></html>`);
  doc.close();

  // Wait for content to render, then print
  setTimeout(() => {
    iframe!.contentWindow?.focus();
    iframe!.contentWindow?.print();
    // Cleanup after print dialog closes
    setTimeout(() => iframe?.remove(), 2000);
  }, 250);
}
