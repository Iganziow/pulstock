// Sentry config para el lado SERVIDOR (Node — SSR + API routes).
// Activación: setear SENTRY_DSN en el .env de producción del frontend.
import * as Sentry from "@sentry/nextjs";

const DSN = process.env.SENTRY_DSN;

if (DSN) {
  Sentry.init({
    dsn: DSN,
    environment: process.env.SENTRY_ENV || "production",
    tracesSampleRate: 0.1,
    // En el server NO hace falta replay (no hay browser).
  });
}
