import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
// Extract origin (scheme + host) from the API URL for CSP connect-src
const apiOrigin = (() => {
  try {
    const u = new URL(apiUrl);
    return `${u.protocol}//${u.host}`;
  } catch {
    return "http://localhost:8000";
  }
})();

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-XSS-Protection", value: "1; mode=block" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  // unsafe-eval needed by Next.js dev / webpack
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      // connect-src incluye Sentry para que el SDK pueda mandar eventos.
      // Si no hay DSN configurado, el SDK no hace requests — el dominio en
      // CSP no abre vulnerabilidad por sí solo.
      `connect-src 'self' ${apiOrigin} https://*.ingest.sentry.io https://*.sentry.io`,
      "img-src 'self' data: blob:",
      "font-src 'self' https://fonts.gstatic.com",
      // worker-src 'self' blob: para que Sentry Replay pueda crear workers
      // de session replay (recordings de UI antes del error). Sin esto, CSP
      // cae al fallback de script-src y bloquea blob: workers.
      "worker-src 'self' blob:",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  // "standalone" solo para Docker. Vercel no lo necesita.
  // Descomentar si se despliega con Docker en Hetzner:
  // output: "standalone",

  // Suppress cross-origin warning for the dev preview proxy
  allowedDevOrigins: ["127.0.0.1", "localhost"],

  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

// Wrappear con Sentry SI tenemos DSN. El AUTH_TOKEN es opcional — si está,
// se suben source maps al build (stack traces legibles); si no, solo se
// activa el SDK runtime (errores se capturan pero traces son minificados).
//
// IMPORTANTE: el wrapper `withSentryConfig` es lo que hace que los archivos
// sentry.client.config.ts / sentry.server.config.ts / sentry.edge.config.ts
// se incluyan en el bundle. SIN el wrapper, esos configs son código muerto.
const SENTRY_DSN_PRESENT = !!process.env.SENTRY_DSN || !!process.env.NEXT_PUBLIC_SENTRY_DSN;

let exportedConfig: NextConfig | unknown = nextConfig;

if (SENTRY_DSN_PRESENT) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { withSentryConfig } = require("@sentry/nextjs");

    // Solo configurar source maps upload si tenemos auth token.
    const sentryWebpackOptions: Record<string, unknown> = {
      silent: !process.env.CI,
      // No tirar errores de build si Sentry falla.
      disableLogger: true,
    };

    if (process.env.SENTRY_AUTH_TOKEN && process.env.SENTRY_ORG && process.env.SENTRY_PROJECT) {
      sentryWebpackOptions.org = process.env.SENTRY_ORG;
      sentryWebpackOptions.project = process.env.SENTRY_PROJECT;
      sentryWebpackOptions.authToken = process.env.SENTRY_AUTH_TOKEN;
      sentryWebpackOptions.widenClientFileUpload = true;
      sentryWebpackOptions.hideSourceMaps = true;
      // Tunelizar requests para evitar adblockers.
      sentryWebpackOptions.tunnelRoute = "/monitoring/sentry";
    } else {
      // Sin auth token — desactivar upload explícitamente para evitar warning.
      sentryWebpackOptions.sourcemaps = { disable: true };
    }

    exportedConfig = withSentryConfig(nextConfig, sentryWebpackOptions);
  } catch {
    // @sentry/nextjs no instalado — uso config plano. Esto NO debería pasar
    // en prod (lo instalamos junto con package.json), pero protege de un
    // build CI sin las deps de monitoring.
    exportedConfig = nextConfig;
  }
}

export default exportedConfig as NextConfig;
