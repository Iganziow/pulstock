/**
 * Pulstock Service Worker — mínimo para instalabilidad PWA.
 * SaaS solo en línea: sin caché ni intercepción de fetch.
 *
 * Nota: NO registramos un handler de "fetch". Si lo hiciéramos, la re-emisión
 * desde el SW se evalúa contra el connect-src del CSP del documento,
 * bloqueando recursos cross-origin (Google Fonts, etc.). Sin handler, las
 * peticiones van directo a la red sin pasar por el SW.
 */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
