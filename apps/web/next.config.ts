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

// Wrappear con Sentry SOLO si está habilitado por flag en build.
// Sin SENTRY_DSN o SENTRY_AUTH_TOKEN, exportamos el config plano.
// Esto evita que el build local/CI falle si las deps de @sentry/nextjs no
// están instaladas, o que se intente subir source maps sin auth token.
const SENTRY_ENABLED =
  !!process.env.SENTRY_DSN && !!process.env.SENTRY_AUTH_TOKEN;

let exportedConfig: NextConfig | unknown = nextConfig;

if (SENTRY_ENABLED) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { withSentryConfig } = require("@sentry/nextjs");
    exportedConfig = withSentryConfig(nextConfig, {
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      silent: !process.env.CI,
      // Subir source maps al build → stack traces legibles en Sentry.
      widenClientFileUpload: true,
      // Tunelizar requests para evitar adblockers (opcional).
      tunnelRoute: "/monitoring/sentry",
      // No tirar errores de build si Sentry falla.
      hideSourceMaps: true,
      disableLogger: true,
    });
  } catch {
    // @sentry/nextjs no instalado — uso config plano.
    exportedConfig = nextConfig;
  }
}

export default exportedConfig as NextConfig;
