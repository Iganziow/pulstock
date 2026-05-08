/**
 * Config Playwright LOCAL — para correr E2E contra dev server, NUNCA prod.
 *
 * Uso:
 *   1. Asegurarse que API + web dev estén corriendo en otra terminal:
 *        cd apps/api && python manage.py runserver 0.0.0.0:8000
 *        cd apps/web && npm run dev
 *   2. Sembrar tenant E2E:
 *        cd apps/api && python manage.py seed_e2e
 *   3. Correr tests:
 *        cd apps/web && npm run test:e2e:local
 *   4. Limpieza:
 *        cd apps/api && python manage.py seed_e2e --cleanup
 *
 * Por qué config separado: el playwright.config.ts default apunta a
 * 65.108.148.200 (prod). Mezclar tests E2E que ESCRIBEN datos contra
 * prod es una receta para corromper data de Mario. Este config los
 * mantiene aislados en local.
 */
import { defineConfig, devices } from "@playwright/test";
import path from "path";

export default defineConfig({
  testDir: "./e2e",
  // Login una sola vez al inicio (evita el rate-limit de 10/min).
  globalSetup: require.resolve("./e2e/global-setup"),
  // Solo los specs que sé que están escritos para correr en local con
  // el tenant e2e-test sembrado.
  testMatch: [
    "tip-withdraw.spec.ts",
    "promotions.spec.ts",
    "sidebar-visibility.spec.ts",
  ],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 60_000,

  use: {
    // Default a 3001 — algunos devs ya tienen otro proceso en 3000.
    // Override con E2E_BASE_URL si Next está en otro puerto.
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3001",
    storageState: path.join(__dirname, "e2e/.auth-state.json"),
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
