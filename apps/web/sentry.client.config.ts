// Sentry config para el lado CLIENTE (browser).
// Captura errores de JS no manejados, fetch fails, etc.
//
// Activación: setear NEXT_PUBLIC_SENTRY_DSN en .env.local / .env de producción.
// Sin DSN, el SDK no se inicializa (cero overhead, cero spam en dev).
import * as Sentry from "@sentry/nextjs";

const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (DSN) {
  Sentry.init({
    dsn: DSN,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENV || "production",

    // Sample 10% de transacciones (performance monitoring).
    tracesSampleRate: 0.1,

    // Replay solo en errores (5% normal + 100% en error). Útil para
    // ver QUÉ hizo el user antes del crash, sin saturar la cuota free.
    replaysSessionSampleRate: 0.0,
    replaysOnErrorSampleRate: 1.0,

    integrations: [
      Sentry.replayIntegration({
        // Mascara texto/inputs por defecto — no exponemos data del cliente.
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],

    // Filtros mínimos: solo browser quirks no accionables y no eventos
    // del usuario. Antes filtrábamos también "Failed to fetch" / 401 pero
    // eso enmascaraba bugs reales. Mejor capturar todo y filtrar en el
    // dashboard de Sentry con "Inbound Filters" si hace falta.
    ignoreErrors: [
      "ResizeObserver loop limit exceeded",
      "ResizeObserver loop completed with undelivered notifications",
      // Errores que dispara el usuario al cancelar uploads/fetches manualmente.
      "AbortError",
    ],
    denyUrls: [
      // Extensions del navegador
      /^chrome-extension:\/\//,
      /^moz-extension:\/\//,
    ],

    // NOTA: removido el `beforeSend` que chequeaba NODE_ENV. Era redundante
    // (el SDK ya está condicionado por la presencia del DSN, y el DSN solo
    // está en .env.local de prod) Y peligroso: en algunos builds de Next.js
    // process.env.NODE_ENV no se sustituía a "production" en el bundle del
    // cliente, lo que descartaba el 100% de los eventos silenciosamente.
  });

  // Exponer el SDK en window.Sentry para debug en producción.
  // Permite hacer desde la consola del browser:
  //   window.Sentry.captureException(new Error("test"));
  // Sin esto, en v8 hay que importar el módulo (no funciona desde devtools).
  if (typeof window !== "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).Sentry = Sentry;
  }
}
