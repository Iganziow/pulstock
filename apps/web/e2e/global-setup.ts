/**
 * Global setup: hace UN SOLO login al inicio de la corrida E2E y guarda el
 * storageState (cookies + localStorage). Cada test lo carga al arrancar
 * sin tener que volver a autenticarse.
 *
 * ¿Por qué? Login está rate-limited a 10/min. Con ~14 tests cada uno
 * haciendo `beforeEach -> login`, se dispara el throttle y los tests
 * fallan con "Solicitud fue regulada".
 *
 * Bonus: corrida ~3-5x más rápida (no hay round-trip de login en cada test).
 */
import { chromium, FullConfig } from "@playwright/test";
import path from "path";

import { E2E_USER, E2E_PASS } from "./_helpers";

export const STORAGE_STATE = path.join(__dirname, ".auth-state.json");

async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL!;
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  await page.goto(`${baseURL}/login`);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  await page.getByPlaceholder("Tu nombre de usuario").fill(E2E_USER);
  await page.locator('input[type="password"]').fill(E2E_PASS);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForURL("**/dashboard**", { timeout: 30000 });

  // Guardamos cookies + localStorage. Cada test lo carga via `use.storageState`.
  await ctx.storageState({ path: STORAGE_STATE });
  await browser.close();
}

export default globalSetup;
