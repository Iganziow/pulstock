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

// Persistencia entre sesiones — guardamos el nombre del último device
// que el user pareó para preferirlo al reabrir la app. Web Bluetooth
// recuerda el permiso del device entre sesiones (a nivel browser/origin),
// pero el cache en memoria se pierde al recargar — usamos
// `navigator.bluetooth.getDevices()` para retomarlo sin picker.
const BT_LAST_DEVICE_NAME_KEY = "pulstock_bt_last_device_name";

function rememberBTDevice(device: any) {
  try {
    if (device?.name) {
      localStorage.setItem(BT_LAST_DEVICE_NAME_KEY, device.name);
    }
  } catch { /* localStorage puede fallar en private mode */ }
}

function getRememberedBTDeviceName(): string | null {
  try {
    return localStorage.getItem(BT_LAST_DEVICE_NAME_KEY);
  } catch { return null; }
}

/**
 * Intenta reconectar a la impresora BT autorizada previamente, SIN abrir
 * el picker. Retorna true si pudo conectar y dejar el device cacheado.
 *
 * Funciona porque:
 *  - Web Bluetooth recuerda el permiso entre sesiones para devices
 *    pareados con `requestDevice()`.
 *  - `navigator.bluetooth.getDevices()` (Chrome ≥85) retorna esos devices
 *    autorizados sin necesitar gesture del user.
 *  - `gatt.connect()` NO requiere gesture (solo `requestDevice()`).
 *
 * Si el browser no soporta `getDevices()` (Firefox, Safari) o si el device
 * no está autorizado, devuelve false sin error → el caller hace fallback
 * al picker normal con `pairBluetoothPrinter()`.
 */
export async function tryReconnectBluetooth(): Promise<boolean> {
  // Logs de diagnóstico — visibles en DevTools del browser. Útil cuando
  // un cliente reporta "tengo que parear cada vez". Agrupados con prefijo
  // [pulstock-bt] para filtrar fácil en consola.
  if (typeof navigator === "undefined" || !navigator.bluetooth) {
    console.log("[pulstock-bt] navigator.bluetooth no disponible");
    return false;
  }
  const bt: any = navigator.bluetooth;
  if (typeof bt.getDevices !== "function") {
    console.log("[pulstock-bt] getDevices() no soportado en este browser — Mario tendrá que apretar el botón cada vez");
    return false;
  }

  try {
    const devices: any[] = await bt.getDevices();
    console.log(`[pulstock-bt] getDevices() retornó ${devices?.length ?? 0} device(s) autorizado(s):`,
      devices?.map((d) => d.name).filter(Boolean));

    if (!devices || devices.length === 0) {
      console.log("[pulstock-bt] sin devices autorizados — necesita parear primero");
      return false;
    }

    const remembered = getRememberedBTDeviceName();
    console.log(`[pulstock-bt] device guardado en localStorage: ${remembered}`);

    const target = (remembered && devices.find((d) => d.name === remembered)) || devices[0];
    if (!target) return false;

    console.log(`[pulstock-bt] reconectando a "${target.name || "(sin nombre)"}"...`);
    cachedBTDevice = target;
    const ch = await connectAndFindCharacteristic(target);
    cachedBTCharacteristic = ch;
    console.log("[pulstock-bt] reconectado OK");
    return true;
  } catch (e) {
    console.warn("[pulstock-bt] reconnect falló:", e);
    cachedBTDevice = null;
    cachedBTCharacteristic = null;
    return false;
  }
}

export async function pairBluetoothPrinter(): Promise<any> {
  if (!navigator.bluetooth) throw new Error("Web Bluetooth no disponible en este navegador");
  const device = await navigator.bluetooth.requestDevice({
    acceptAllDevices: true,
    optionalServices: BT_SERVICES,
  });
  cachedBTDevice = device;
  cachedBTCharacteristic = null;
  rememberBTDevice(device);
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
  rememberBTDevice(device);  // persistir para próximas sesiones
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

// ── Network (via agent) ──────────────────────────────────────────────────────
//
// Histórico: existió un endpoint /api/core/print/network/ que abría el socket
// TCP desde el SERVIDOR. Eso solo funciona si el server está en la misma LAN
// que la impresora — imposible en producción cloud (server fuera de tu red).
//
// Hoy: la impresión por red se hace SIEMPRE a través del Pulstock Printer
// Agent corriendo en un PC del local. El agente sí está en la LAN y abre el
// socket directamente a la impresora. La "PrinterConfig" tipo "network"
// referencia un agentId + una impresora del agente (configurada como
// connection_type='network' con su IP en el panel).
//
// Si quieres probar conectividad a una IP arbitraria desde el navegador,
// usa el endpoint nuevo POST /api/printing/agents/<id>/test-network/
// (TODO próximo) que pide al agente probar el socket localmente.

async function sendNetwork(_data: Uint8Array, _address: string): Promise<void> {
  throw new Error(
    "La impresión por red ahora se hace a través del Pulstock Printer Agent. " +
    "Configura tu impresora de red como una impresora del agente en " +
    "Configuración → Impresoras → Agente."
  );
}

/**
 * Test conectividad a una impresora de red (sin imprimir realmente).
 *
 * Solo funciona si el navegador está en la MISMA LAN que la impresora — no
 * vamos al servidor. Probamos conexión directa por TCP-over-WebSocket... que
 * el navegador no soporta. Por eso este test ya no es realmente "test de
 * red" — devolvemos un mensaje informativo orientando al usuario.
 */
export async function testNetworkPrinter(_address: string): Promise<{ ok: boolean; error?: string }> {
  return {
    ok: false,
    error: (
      "Para probar una impresora de red, configúrala primero como impresora " +
      "del Pulstock Printer Agent. Una vez asociada al agente, usa el botón " +
      "'Imprimir prueba' en la sección de impresoras del agente."
    ),
  };
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
    // Mensajes específicos para ayudar al usuario a diagnosticar.
    if (e instanceof ApiError) {
      if (e.status === 404) {
        throw new Error("Agente no encontrado. Puede que lo hayan eliminado — quita esta impresora y vuelve a agregarla.");
      }
      if (e.status === 402) {
        throw new Error("Suscripción no activa — renueva tu plan para imprimir.");
      }
      if (e.status === 503) {
        // Backend nos avisa que el agente está offline. Antes (sin esta validación)
        // el job se encolaba en silencio y el usuario nunca se enteraba.
        throw new Error(
          (e.data as any)?.detail ||
          `El PC '${printer.name}' está desconectado. Asegúrate de que el computador del local esté prendido.`
        );
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
      // Las impresoras de red ahora se manejan exclusivamente vía el agente
      // PC. Si llegamos acá es porque alguien tiene una config vieja tipo
      // "network" en localStorage — la guiamos a re-configurarla como
      // impresora del agente.
      throw new Error(
        "Las impresoras de red ahora se configuran en el PC del local con " +
        "el Pulstock Printer Agent. Elimina esta impresora y vuelve a " +
        "agregarla como 'Impresora del agente'."
      );
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

// ── Auto-print via PC del local (modelo Fudo) ────────────────────────────────

/**
 * Imprimir vía el agente del local sin necesidad de configurar nada en el
 * dispositivo del usuario. Es el endpoint que el celular/tablet del staff
 * debe usar — no se pregunta nada, simplemente la comanda sale en el PC.
 *
 * El backend elige el agente online (priorizando el de la tienda activa) y
 * encola un job en su impresora por defecto.
 *
 * Devuelve la respuesta del backend si OK; throw con mensaje en español si
 * no hay agente disponible (404) u otro error.
 */
async function printViaLocalAgent(
  data_b64: string | null,
  html: string | null,
  source: string,
): Promise<{ job_id: number; agent_name: string; printer_name: string }> {
  const { apiFetch, ApiError } = await import("@/lib/api");
  try {
    const body: Record<string, unknown> = { source };
    if (data_b64) body.data_b64 = data_b64;
    if (html) body.html = html;
    return await apiFetch("/printing/print/", {
      method: "POST",
      body: JSON.stringify(body),
    });
  } catch (e: any) {
    if (e instanceof ApiError) {
      if (e.status === 404) {
        // El backend nos da el mensaje en e.data.detail con la solución.
        throw new Error(
          (e.data as any)?.detail ||
          "No hay PC del local conectado. Asegúrate de que el computador con el Pulstock Printer Agent esté prendido y con internet."
        );
      }
      if (e.status === 402) {
        throw new Error("Suscripción no activa — renueva tu plan para imprimir.");
      }
    }
    throw e;
  }
}

// ── Universal print orchestrator ─────────────────────────────────────────────

export interface UniversalPrintInput {
  /** Raw ESC/POS bytes (for thermal printers). Optional if only html provided. */
  bytes?: Uint8Array;
  /** HTML receipt — usado por impresión de sistema "kioskoo" o como copia. */
  html: string;
  /** Preferred paper width. */
  paperWidth?: 58 | 80;
  /** Etiqueta del origen del job para auditoría: "pos", "mesa", "manual", "test". */
  source?: string;
  /**
   * Forzar diálogo nativo del navegador (Guardar como PDF / impresora del
   * sistema). Solo úsalo si el usuario explícitamente eligió "Imprimir en
   * este dispositivo" — NO es el flujo por defecto. Para comandas siempre
   * dejar esto false (o no pasarlo).
   */
  forceLocalDialog?: boolean;
}

/**
 * Imprime una comanda. Estrategia (modelo Fudo):
 *
 *   1. Si el usuario configuró una impresora local en este dispositivo
 *      (USB/BLE/agente seleccionado) → usar esa.
 *   2. Si no, mandar al PC del local vía /api/printing/print/ — el agente
 *      del local imprime en su impresora por defecto.
 *   3. Si no hay agente conectado → ERROR claro.  NO caemos al diálogo
 *      "Guardar como PDF" del navegador (eso confundía al staff).
 *
 * El único caso en que abrimos el diálogo nativo es cuando se pasa
 * `forceLocalDialog: true` (ej. botón "Imprimir en este dispositivo").
 */
export async function printUniversal(input: UniversalPrintInput): Promise<{ method: string; ok: boolean; error?: string; printer?: string; cancelled?: boolean }> {
  const p = getDefaultPrinter();
  const width: 58 | 80 = input.paperWidth || p?.paperWidth || 80;
  const source = input.source || "web";

  // (a) Override explícito del usuario: usa el diálogo nativo.
  if (input.forceLocalDialog) {
    try {
      printHTML(input.html, width);
      return { method: "system", ok: true };
    } catch (e: any) {
      return { method: "system", ok: false, error: e?.message || "Error al imprimir" };
    }
  }

  // (b) Impresora local configurada en este dispositivo (BLE/USB/agente
  //     específico). Es el flujo "tengo mi propia impresora conectada acá".
  if (p && p.type !== "system" && input.bytes) {
    // Si es BT y todavía no hay device cacheado en esta sesión, intentamos
    // reconectar via getDevices() — el browser puede haber autorizado el
    // device en sesiones previas y getDevices() lo retorna sin abrir picker.
    // Esto evita el caso "el user cierra/reabre la app y BT requiere
    // reparear" que reportaba Mario.
    if (p.type === "bluetooth") {
      try { await tryReconnectBluetooth(); } catch { /* falla silenciosa */ }
    }

    try {
      await printBytes(input.bytes, p);
      return { method: p.type, ok: true, printer: p.name };
    } catch (localErr: any) {
      const localErrMsg = localErr?.message || String(localErr);

      // Si el user CANCELÓ el picker (BT/USB), NO es un error real — es
      // decisión consciente. Retornamos `cancelled: true` para que el
      // caller silencie el banner rojo.
      const wasCancelled = /user cancell?ed|user dismissed|user denied|user aborted|notallowederror|aborterror/i.test(localErrMsg);
      if (wasCancelled) {
        return {
          method: p.type, ok: false, cancelled: true,
          error: "Cancelaste la selección de impresora.",
        };
      }

      // NO caemos al fallback del agente PC. Antes lo hacíamos pero el
      // mensaje resultante mezclaba errores ("No hay agentes...") cuando
      // en realidad el problema era la impresora local — confunde mucho
      // al user. Si tiene impresora local configurada, asumimos que es la
      // que quiere usar y mostramos el error real de esa impresora.
      return {
        method: "failed", ok: false,
        error: `No se pudo imprimir en "${p.name}": ${localErrMsg}. Revisa que la impresora esté encendida y conectada por Bluetooth.`,
      };
    }
  }

  // (c) Flujo por defecto del modelo Fudo: ir directo al PC del local.
  try {
    const data_b64 = input.bytes ? bytesToB64(input.bytes) : null;
    const r = await printViaLocalAgent(data_b64, input.html || null, source);
    return { method: "agent-auto", ok: true, printer: r.printer_name };
  } catch (e: any) {
    // NO caemos al diálogo nativo. El usuario ve un error claro y sabe
    // qué hacer (prender el PC, llamar al admin, etc.).
    return {
      method: "failed", ok: false,
      error: e?.message || "No se pudo imprimir.",
    };
  }
}

function bytesToB64(data: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < data.byteLength; i++) {
    binary += String.fromCharCode(data[i]);
  }
  return btoa(binary);
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
