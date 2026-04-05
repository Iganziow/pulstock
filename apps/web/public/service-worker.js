/**
 * Pulstock Service Worker — minimal for PWA installability.
 * No offline cache (online-only SaaS). Just enough for Chrome "Install app" prompt.
 */

const CACHE_NAME = "pulstock-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Pass-through: all requests go to network
  event.respondWith(fetch(event.request));
});
