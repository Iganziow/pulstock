// Sentry config para el Edge runtime (middleware + edge routes).
import * as Sentry from "@sentry/nextjs";

const DSN = process.env.SENTRY_DSN;

if (DSN) {
  Sentry.init({
    dsn: DSN,
    environment: process.env.SENTRY_ENV || "production",
    tracesSampleRate: 0.1,
  });
}
