/**
 * Traductor de errores del browser/API a mensajes amigables en español.
 *
 * Los APIs del browser (WebUSB, WebBluetooth, fetch, etc.) tiran mensajes
 * crudos en inglés tipo "User cancelled the requestDevice() chooser." que
 * son inscrutables para un usuario no-técnico.
 *
 * Este helper mapea esos patrones a mensajes claros en español. Si no
 * encuentra match, devuelve el fallback (o el mensaje original humanizado).
 *
 * Uso:
 *   import { humanizeError } from "@/lib/errors";
 *   try { ... } catch (e) { flash("err", humanizeError(e, "Error al imprimir")); }
 */

export interface HumanizeOptions {
  /** Fallback si no matchea ningún patrón. Default: "Ocurrió un error" */
  fallback?: string;
  /** Si true, incluye el mensaje técnico original entre paréntesis (útil en modo debug) */
  includeTechnical?: boolean;
}

/**
 * Diccionario patrón-en-inglés → mensaje-en-español.
 * Se evalúan en orden; el primer match gana.
 * Los patrones son RegExp case-insensitive.
 */
const ERROR_TRANSLATIONS: Array<{ pattern: RegExp; message: string }> = [
  // ── WebUSB / WebBluetooth (picker cancelado) ──
  {
    pattern: /user cancell?ed|user dismissed/i,
    message: "Cancelaste la selección. Si querés reintentar, presiona el botón de nuevo.",
  },
  {
    pattern: /no device selected|must provide a device/i,
    message: "No seleccionaste ningún dispositivo. Por favor elige uno de la lista y acepta.",
  },
  {
    pattern: /device not found|no devices found|no such device/i,
    message: "No se encontraron dispositivos. Verifica que esté encendido y conectado al PC.",
  },
  {
    pattern: /webusb.*not available|webusb.*not supported|navigator\.usb/i,
    message: "Tu navegador no soporta WebUSB. Usa Chrome o Edge en un PC (no funciona en iPhone).",
  },
  {
    pattern: /web.?bluetooth.*not available|bluetooth.*not supported|navigator\.bluetooth/i,
    message: "Tu navegador no soporta Bluetooth web. Usa Chrome en Android o PC.",
  },
  {
    pattern: /bluetooth adapter not available|no bluetooth adapter/i,
    message: "Bluetooth no está disponible en este equipo. Activalo en configuración del sistema.",
  },
  {
    pattern: /gatt.*failed|connection.*cancell?ed|gatt error/i,
    message: "La conexión Bluetooth se perdió. Acerca el dispositivo y reintenta.",
  },

  // ── HTTP / Network ──
  {
    pattern: /failed to fetch|network.*error|networkerror/i,
    message: "Sin conexión al servidor. Revisa tu internet y reintenta.",
  },
  {
    pattern: /timeout|timed out|request.*abort/i,
    message: "El servidor tardó demasiado en responder. Intenta de nuevo.",
  },
  {
    pattern: /cors|cross[- ]origin/i,
    message: "Error de permisos del navegador. Refresca la página e intenta de nuevo.",
  },

  // ── Auth / Session ──
  {
    pattern: /unauthorized|401|session expired/i,
    message: "Tu sesión expiró. Por favor inicia sesión nuevamente.",
  },
  {
    pattern: /forbidden|403|no permission/i,
    message: "No tienes permisos para esta acción.",
  },
  {
    pattern: /not found|404/i,
    message: "Recurso no encontrado. Puede haber sido eliminado.",
  },

  // ── Impresora específica ──
  {
    pattern: /no.*printer.*configured|no hay impresora/i,
    message: "No tienes impresora configurada. Ve a Configuración → Impresoras.",
  },
  {
    pattern: /printer offline|printer disconnected/i,
    message: "La impresora está desconectada o apagada.",
  },
  {
    pattern: /paper (out|jam)|out of paper/i,
    message: "La impresora se quedó sin papel o está trabada.",
  },
  {
    pattern: /access denied|permission denied/i,
    message: "El navegador bloqueó el acceso al dispositivo. Permite el permiso e intenta de nuevo.",
  },

  // ── Flow / Pagos ──
  {
    pattern: /payment.*rejected|card.*declined/i,
    message: "El pago fue rechazado por la tarjeta. Intenta con otra o contacta a tu banco.",
  },
  {
    pattern: /amount mismatch/i,
    message: "Monto inválido. Recarga la página e intenta de nuevo.",
  },

  // ── Generic JS errors que no queremos mostrar crudos ──
  {
    pattern: /cannot read propert|undefined is not|null is not|typeerror/i,
    message: "Ocurrió un error inesperado. Refresca la página e intenta de nuevo.",
  },
  {
    pattern: /failed to execute/i,
    message: "La acción no se pudo completar. Intenta de nuevo.",
  },
];

/**
 * Extrae un mensaje de error amigable en español desde cualquier tipo de excepción.
 */
export function humanizeError(e: unknown, fallback = "Ocurrió un error"): string {
  const raw = extractMessage(e);
  if (!raw) return fallback;

  // Buscar patrón conocido
  for (const { pattern, message } of ERROR_TRANSLATIONS) {
    if (pattern.test(raw)) return message;
  }

  // Si parece un mensaje técnico en inglés (contiene palabras como "Failed",
  // "Error", "Cannot", "Invalid"), usamos el fallback.
  if (/\b(failed|error|cannot|invalid|undefined|null|typeerror|syntaxerror)\b/i.test(raw)) {
    return fallback;
  }

  // Si el mensaje parece estar en español o ser corto+legible, lo mostramos
  if (raw.length < 200 && !/^[a-zA-Z'`]+\s*\(/.test(raw)) {
    return raw;
  }

  return fallback;
}

/**
 * Detecta si un error vino de que el usuario canceló el picker del browser
 * (Web Bluetooth `requestDevice()`, WebUSB `requestDevice()`, file picker).
 * No es un error real — es decisión del user.
 *
 * Uso típico:
 *   try { await print(...) }
 *   catch (e) {
 *     if (isUserCancellation(e)) return; // silencio, no hacer nada
 *     showError(humanizeError(e));
 *   }
 */
export function isUserCancellation(e: unknown): boolean {
  const raw = extractMessage(e);
  if (!raw) return false;
  return /user cancell?ed|user dismissed|user denied|user aborted|notallowederror|aborterror/i.test(raw);
}

function extractMessage(e: unknown): string {
  if (!e) return "";
  if (typeof e === "string") return e;
  if (typeof e === "object") {
    const anyE = e as any;
    // ApiError custom: e.data.detail > e.message
    if (anyE.data?.detail) {
      if (typeof anyE.data.detail === "string") return anyE.data.detail;
      if (typeof anyE.data.detail === "object") {
        // Ej: { email: "inválido" } → primer valor
        const firstVal = Object.values(anyE.data.detail)[0];
        if (typeof firstVal === "string") return firstVal;
        if (Array.isArray(firstVal) && typeof firstVal[0] === "string") return firstVal[0];
      }
    }
    if (typeof anyE.message === "string") return anyE.message;
  }
  return String(e);
}
