// Sentry config para el lado CLIENTE (browser).
// Captura errores de JS no manejados, fetch fails, etc.
//
// Activación: setear NEXT_PUBLIC_SENTRY_DSN en .env.local / .env de producción.
// Sin DSN, el SDK no se inicializa ni se descarga (cero overhead).
//
// (15/05/26) LAZY LOAD: antes el `import * as Sentry from "@sentry/nextjs"`
// al tope del archivo metía 163 KB brotli (515 KB raw) de SDK en el chunk
// SHARED de TODAS las páginas. Resultado: cada vista de Mario descargaba
// 225 KB brotli de los cuales 163 eran Sentry — ~3 segundos extra en su
// 4G del cafetería.
//
// Ahora: dynamic `await import(...)` → webpack crea chunk separado de
// Sentry que NO se descarga inicialmente. Lo cargamos via
// requestIdleCallback DESPUÉS de que la app sea interactiva (TTI), o con
// fallback setTimeout 1.5s. Mario interactúa con la UI antes de que
// Sentry siquiera empiece a descargarse.
//
// Trade-off conocido: en los primeros 1-3 segundos no capturamos errores
// JS. En la práctica eso es aceptable — los errores que importan suelen
// pasar cuando el usuario interactúa, y para entonces Sentry ya está
// inicializado.

if (typeof window !== "undefined" && process.env.NEXT_PUBLIC_SENTRY_DSN) {
  const initSentry = async () => {
    try {
      const Sentry = await import("@sentry/nextjs");

      Sentry.init({
        dsn: process.env.NEXT_PUBLIC_SENTRY_DSN!,
        environment: process.env.NEXT_PUBLIC_SENTRY_ENV || "production",

        // Sample 10% de transacciones (performance monitoring).
        tracesSampleRate: 0.1,

        // Replay solo en errores. Útil para ver QUÉ hizo el user antes
        // del crash, sin saturar la cuota free.
        replaysSessionSampleRate: 0.0,
        replaysOnErrorSampleRate: 1.0,

        integrations: [
          Sentry.replayIntegration({
            // Mascara texto/inputs por defecto — no exponemos data del cliente.
            maskAllText: true,
            blockAllMedia: true,
          }),
        ],

        ignoreErrors: [
          "ResizeObserver loop limit exceeded",
          "ResizeObserver loop completed with undelivered notifications",
          "AbortError",
        ],
        denyUrls: [
          /^chrome-extension:\/\//,
          /^moz-extension:\/\//,
        ],
      });

      // Exponer SDK en window.Sentry para debug en producción.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).Sentry = Sentry;
    } catch (err) {
      // Si falla la carga del chunk (network, adblocker), no bloqueamos
      // la app. Sentry no aparecerá pero el resto funciona.
      // eslint-disable-next-line no-console
      console.warn("[sentry] lazy load failed:", err);
    }
  };

  // requestIdleCallback: navegador sólo carga Sentry cuando tiene tiempo
  // libre, después de que la app es interactiva. Timeout 3s = peor caso
  // forzar la carga si el navegador siempre está ocupado.
  // Fallback setTimeout 1.5s para Safari (que aún no soporta rIC).
  if ("requestIdleCallback" in window) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).requestIdleCallback(initSentry, { timeout: 3000 });
  } else {
    setTimeout(initSentry, 1500);
  }
}
