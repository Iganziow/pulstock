/**
 * E2E: flujo de retiro de propinas — feature del commit 638cf83.
 *
 * Cubre:
 *  - Botón "💸 Retirar propinas" en /dashboard/caja (sólo con sesión abierta)
 *  - Botón "💸 Retirar propinas" en /dashboard/propinas (siempre visible)
 *  - Modal con validación de monto + descripción opcional
 *  - Mensaje "No hay caja abierta" si no hay sesión
 *  - Que el movimiento creado tenga categoría TIP_WITHDRAW (verifica vía API)
 *
 * No usa la cuenta de Mario — apunta al tenant E2E aislado.
 */
import { test, expect } from "@playwright/test";
import { ensureOpenCashSession, closeAnyOpenSession } from "./_helpers";

test.describe("Retiro de propinas", () => {
  test.beforeEach(async ({ page }) => {
    // Autenticación cargada por storageState. Vamos al dashboard para
    // que `closeAnyOpenSession` pueda leer el access token de localStorage.
    await page.goto("/dashboard");
  });

  test.afterEach(async ({ page }) => {
    // Cerrar la sesión que abrimos en cada test, así el siguiente arranca limpio.
    await closeAnyOpenSession(page);
  });

  test("/dashboard/caja: botón 'Retirar propinas' aparece con sesión abierta", async ({ page }) => {
    await ensureOpenCashSession(page);
    await page.goto("/dashboard/caja");
    await page.waitForLoadState("networkidle");

    // El botón existe en el header de la página (mensaje 638cf83).
    const btn = page.getByRole("button", { name: /retirar propinas/i });
    await expect(btn).toBeVisible({ timeout: 10000 });
  });

  test("/dashboard/propinas: el botón aparece siempre", async ({ page }) => {
    await page.goto("/dashboard/propinas");
    await page.waitForLoadState("networkidle");

    const btn = page.getByRole("button", { name: /retirar propinas/i });
    await expect(btn).toBeVisible({ timeout: 10000 });
  });

  test("/dashboard/propinas sin sesión abierta: el modal muestra '🔒 No hay caja abierta'", async ({ page }) => {
    // Asegurar que NO hay sesión
    await closeAnyOpenSession(page);
    await page.goto("/dashboard/propinas");
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /retirar propinas/i }).click();

    // El modal debe mostrar el mensaje pedagógico (commit 638cf83).
    await expect(page.getByText(/no hay caja abierta/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("button", { name: /entendido/i })).toBeVisible();

    // Cerrar el modal
    await page.getByRole("button", { name: /entendido/i }).click();
  });

  test("modal valida monto: botón Confirmar deshabilitado con monto vacío o 0", async ({ page }) => {
    await ensureOpenCashSession(page);
    await page.goto("/dashboard/caja");
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /retirar propinas/i }).click();

    const confirmBtn = page.getByRole("button", { name: /confirmar retiro/i });
    await expect(confirmBtn).toBeVisible({ timeout: 5000 });
    await expect(confirmBtn).toBeDisabled();

    // Ingresar 0 — sigue deshabilitado (numAmount <= 0)
    const amtInput = page.getByPlaceholder("$0").first();
    await amtInput.fill("0");
    await expect(confirmBtn).toBeDisabled();

    // Ingresar monto válido — se habilita
    await amtInput.fill("1000");
    await expect(confirmBtn).toBeEnabled();
  });

  test("happy path: registrar retiro de $1.000 y verificar en backend", async ({ page, baseURL }) => {
    await ensureOpenCashSession(page, 50000);
    await page.goto("/dashboard/caja");
    await page.waitForLoadState("networkidle");

    // Antes del retiro — capturar movimientos vía API
    const apiURL = baseURL!.replace(/:300\d/, ":8000") + "/api";
    const token = await page.evaluate(() => localStorage.getItem("access"));
    const before = await page.request.get(`${apiURL}/caja/sessions/current/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const beforeData = await before.json();
    const beforeOuts = (beforeData.movements || []).filter((m: any) =>
      m.category === "TIP_WITHDRAW"
    ).length;

    // Disparar el flujo del frontend
    await page.getByRole("button", { name: /retirar propinas/i }).click();
    await page.getByPlaceholder("$0").first().fill("1000");
    // El campo "quien retiró" es opcional — lo llenamos para verificar la descripción
    await page.getByPlaceholder(/ignacia|nadia|equipo/i).fill("E2E Tester");
    await page.getByRole("button", { name: /confirmar retiro/i }).click();

    // Esperar que el modal cierre
    await expect(page.getByRole("button", { name: /confirmar retiro/i })).toHaveCount(0, { timeout: 8000 });

    // Verificar en backend: hay un movimiento más con categoría TIP_WITHDRAW
    const after = await page.request.get(`${apiURL}/caja/sessions/current/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const afterData = await after.json();
    const tipWithdraws = (afterData.movements || []).filter((m: any) =>
      m.category === "TIP_WITHDRAW"
    );
    expect(tipWithdraws.length).toBe(beforeOuts + 1);

    const last = tipWithdraws[tipWithdraws.length - 1];
    expect(Number(last.amount)).toBe(1000);
    expect(last.type).toBe("OUT");
    // La descripción incluye "E2E Tester"
    expect(last.description).toContain("E2E Tester");
  });
});
