import { extractErr } from "@/lib/format";

/**
 * Traduce el error técnico del backend a algo que una persona que acaba de
 * pagar pueda entender y accionar.
 *
 * Recibe `unknown` a propósito. El 02/09/26 la pantalla de resultado del pago
 * se caía entera —"Error inesperado", pantalla en blanco con un botón— cuando
 * el token del enlace no era un UUID. DRF responde en ese caso:
 *
 *     {"detail": ["“x” no es un UUID válido."]}
 *
 * Una LISTA, no un texto. La página guardaba eso tal cual y esta función le
 * hacía `.toLowerCase()` encima. Lo único que se puede asumir del `detail` de
 * DRF es que no se puede asumir su forma: texto, lista, u objeto por campo.
 * Por eso pasa por `extractErr`, que ya sabe aplanar las tres.
 *
 * Vive fuera de `page.tsx` porque Next no permite exportar nada más que la
 * página desde ese archivo, y esto tiene que poder probarse solo.
 */
export type AccionPrincipal = "back" | "retry" | "support";

export type ErrorAmigable = {
  title: string;
  message: string;
  primaryAction: AccionPrincipal;
};

export const CORREO_SOPORTE = "pulstock.admin@gmail.com";

export function friendlyError(rawError: unknown, hasToken: boolean): ErrorAmigable {
  const texto = extractErr({ data: rawError }, "");
  const e = texto.toLowerCase();

  if (!hasToken) {
    return {
      title: "Esta página no es accesible directamente",
      message: "Llegaste aquí por error. Esta pantalla solo se abre desde el enlace que envía Flow después de pagar. Vuelve a planes para iniciar el proceso.",
      primaryAction: "back",
    };
  }
  // El token viene, pero no tiene forma de token: suele pasar al copiar el
  // enlace a mano desde un correo y perder un pedazo. Decirle "no es un UUID
  // válido" a quien acaba de pagar no le sirve de nada.
  if (e.includes("uuid") || (e.includes("token") && (e.includes("inválido") || e.includes("invalido")))) {
    return {
      title: "El enlace de pago no es válido",
      message: "El código del enlace está incompleto o alterado — pasa al copiarlo a mano. Vuelve a abrirlo desde el correo de Flow, o inicia una nueva sesión desde la página de planes.",
      primaryAction: "back",
    };
  }
  if (e.includes("token") && (e.includes("no proporcionado") || e.includes("requerido"))) {
    return {
      title: "Falta el código de la sesión",
      message: "El enlace de pago está incompleto. Inicia una nueva sesión de pago desde la página de planes.",
      primaryAction: "back",
    };
  }
  if (e.includes("sesión no encontrada") || e.includes("session not found") || e.includes("404")) {
    return {
      title: "No encontramos esta sesión de pago",
      message: "El enlace puede haber expirado, o la sesión fue eliminada. Inicia una nueva desde planes.",
      primaryAction: "back",
    };
  }
  if (e.includes("conexión") || e.includes("network") || e.includes("failed to fetch")) {
    return {
      title: "Sin conexión a internet",
      message: "Verifica tu WiFi o datos móviles y presiona Reintentar.",
      primaryAction: "retry",
    };
  }
  return {
    title: "Algo no salió como esperábamos",
    message: texto || `No pudimos cargar la información del pago. Prueba Reintentar; si el problema continúa, escríbenos a ${CORREO_SOPORTE}.`,
    primaryAction: "support",
  };
}
