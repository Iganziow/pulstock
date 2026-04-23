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

    // Filtros: errores que sabemos que NO queremos en el dashboard.
    ignoreErrors: [
      // Browser quirks no accionables
      "ResizeObserver loop limit exceeded",
      "ResizeObserver loop completed with undelivered notifications",
      // Network: ya tenemos UI que avisa al user, no hace falta alertar.
      "Failed to fetch",
      "NetworkError",
      "Load failed",
      // 401 esperado tras token refresh — el código ya lo maneja.
      /401/,
    ],
    denyUrls: [
      // Extensions del navegador
      /^chrome-extension:\/\//,
      /^moz-extension:\/\//,
    ],

    // Antes de mandar, sanitizá el evento.
    beforeSend(event) {
      // No mandar si no estamos en producción real (precaución extra).
      if (process.env.NODE_ENV !== "production") return null;
      return event;
    },
  });
}
