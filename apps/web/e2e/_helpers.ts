/**
 * Helpers compartidos por los E2E tests locales (tip-withdraw, promotions,
 * sidebar-visibility). Asume que `python manage.py seed_e2e` corrió antes.
 */
import { Page, expect } from "@playwright/test";

export const E2E_USER = "e2e_test";
export const E2E_PASS = "E2eTest2026!";

/**
 * Login limpio. NO se usa habitualmente — el global-setup hace login
 * UNA SOLA VEZ al arranque y cada test arranca autenticado vía
 * storageState. Mantengo la función por si algún test específico
 * necesita login fresco (ej. test de logout).
 *
 * Si la llamás desde un test, vas a chocar con el rate-limit de 10/min.
 */
export async function loginE2E(page: Page) {
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForLoadState("domcontentloaded");

  const userInput = page.getByPlaceholder("Tu nombre de usuario");
  await userInput.waitFor({ state: "visible", timeout: 15000 });
  await userInput.fill(E2E_USER);
  await page.locator('input[type="password"]').fill(E2E_PASS);
  await page.getByRole("button", { name: "Ingresar" }).click();

  await page.waitForURL("**/dashboard**", { timeout: 25000 });
}

/** Abre una caja con monto inicial. Necesario para crear movimientos.
 *
 * Layout actual de /dashboard/caja:
 *   - Si no hay sesión abierta: tab "Arqueo activo" muestra un FORM inline
 *     ("Abrir nuevo arqueo") con select de caja + input monto inicial +
 *     botón "Abrir arqueo".
 *   - Si ya hay sesión: botón "Cerrar arqueo" en el header.
 */
export async function ensureOpenCashSession(page: Page, initial = 10000) {
  await page.goto("/dashboard/caja");
  await page.waitForLoadState("networkidle");

  // Si ya hay sesión, el botón "Cerrar arqueo" aparece — early return.
  const closeBtn = page.getByRole("button", { name: /cerrar.*arqueo/i });
  if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) return;

  // Form inline. Seleccionar la caja del seeder (E2E Caja).
  const select = page.locator("select").first();
  await select.waitFor({ state: "visible", timeout: 5000 });
  // El primer <option> es el placeholder "-- Selecciona --". Tomamos el segundo.
  const opts = await select.locator("option").all();
  if (opts.length < 2) {
    throw new Error("No hay cajas registradas para abrir arqueo. ¿Corriste seed_e2e?");
  }
  const optValue = await opts[1].getAttribute("value");
  await select.selectOption(optValue!);

  // Input "Fondo inicial". Placeholder es "$0".
  const amtInput = page.getByPlaceholder("$0").first();
  await amtInput.waitFor({ state: "visible", timeout: 5000 });
  await amtInput.fill(String(initial));

  await page.getByRole("button", { name: /^abrir arqueo$/i }).click();
  await page.waitForLoadState("networkidle");
  // Verifica que ahora SÍ hay sesión (apareció el botón cerrar)
  await closeBtn.waitFor({ state: "visible", timeout: 10000 });
}

/** Cierra una sesión abierta (cleanup entre tests).
 * Usa la API directamente — más rápido y robusto que clickear el modal.
 */
export async function closeAnyOpenSession(page: Page) {
  const apiURL = (await page.evaluate(() => window.location.origin))
    .replace(/:300\d/, ":8000") + "/api";
  const token = await page.evaluate(() => localStorage.getItem("access"));
  if (!token) return;

  // Pedir sesión actual; si no hay, listo.
  const cur = await page.request.get(`${apiURL}/caja/sessions/current/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (cur.status() === 404) return;
  const session = await cur.json();

  // Cerrar via endpoint /close/ con counted_cash=expected (sin diferencia)
  const expected = session.live?.expected_cash ?? "0";
  await page.request.post(`${apiURL}/caja/sessions/${session.id}/close/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { counted_cash: String(expected) },
  });
}

/**
 * Llama al backend directo para limpiar cualquier promoción que el test
 * haya creado en el tenant E2E. Usa el access_token del localStorage.
 */
export async function deleteAllPromotions(page: Page, baseURL: string) {
  const apiURL = baseURL.replace(/:300\d/, ":8000") + "/api";
  const token = await page.evaluate(() => localStorage.getItem("access"));
  if (!token) return;

  const list = await page.request.get(`${apiURL}/promotions/?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!list.ok()) return;
  const data = await list.json();
  const promos: { id: number }[] = data.results || [];
  for (const p of promos) {
    await page.request.delete(`${apiURL}/promotions/${p.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
}
