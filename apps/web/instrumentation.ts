// Next.js instrumentation hook (15.2+).
// Se ejecuta UNA VEZ al arrancar cada runtime (Node y Edge).
//
// Sentry v8 + Next.js 15.2+ ya NO carga sentry.server.config.ts ni
// sentry.edge.config.ts automáticamente — hay que importarlos desde acá.
//
// Para el cliente (browser), Next.js 15.2+ usa `instrumentation-client.ts`
// (nombre fijo, sin import explícito).
//
// Docs: https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

// Hook opcional para capturar errores de los Server Components / SSR.
// Lo proxieamos a Sentry.
export async function onRequestError(
  err: unknown,
  request: { path: string; method: string; headers: Record<string, string | string[]> },
  context: { routerKind: string; routePath: string; routeType: string },
) {
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(err, request, context);
}
