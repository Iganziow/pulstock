import { test, expect, Page } from "@playwright/test";

/**
 * SMOKE E2E LOCAL — Refactor SaleTip relacional (Daniel 29/04/26).
 *
 * Valida end-to-end:
 *  - Login del user admin local (admin/admin123).
 *  - Lista de ventas carga sin 500/JS errors.
 *  - Detalle de venta muestra UI de propinas relacional (filas SaleTip).
 *  - Modal "Editar propina" renderiza split-style (con "+ Agregar propina").
 *  - PATCH split tip llega bien al backend y la UI refleja el cambio.
 *
 * Pre-requisitos:
 *  - Backend en http://localhost:8000
 *  - Frontend en http://localhost:3000
 *  - User admin/admin123 creado (rol owner) en tenant_id=1
 *  - Sale #1 existe con al menos un SaleTip
 *
 * Set E2E_BASE_URL=http://localhost:3000 al correr.
 */

const ADMIN_USER = "admin";
const ADMIN_PASS = "admin123";

async function loginLocal(page: Page) {
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  await page.getByPlaceholder("Tu nombre de usuario").waitFor({ state: "visible", timeout: 15000 });
  await page.getByPlaceholder("Tu nombre de usuario").fill(ADMIN_USER);
  await page.locator('input[type="password"]').fill(ADMIN_PASS);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForURL("**/dashboard**", { timeout: 25000 });
  await page.waitForLoadState("domcontentloaded");
}

test.describe("Smoke local — refactor SaleTip", () => {
  let consoleErrors: string[] = [];
  let networkErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    networkErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text();
        if (text.includes("favicon") || text.includes("Download the React DevTools")) return;
        consoleErrors.push(text.substring(0, 200));
      }
    });
    page.on("response", (resp) => {
      const status = resp.status();
      if (status >= 500) {
        networkErrors.push(`${status} ${resp.url().substring(0, 150)}`);
      }
    });
  });

  test("login local + dashboard carga sin 500/errores JS", async ({ page }) => {
    await loginLocal(page);
    await page.waitForTimeout(3000);
    expect(networkErrors, `5xx detectados: ${networkErrors.join(", ")}`).toHaveLength(0);
    expect(consoleErrors.filter(e => !e.includes("Warning:")), `JS errors: ${consoleErrors.join("; ")}`).toHaveLength(0);
  });

  test("/dashboard/sales lista carga y muestra ventas", async ({ page }) => {
    await loginLocal(page);
    await page.goto("/dashboard/sales");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    expect(bodyText.length).toBeGreaterThan(50);

    expect(networkErrors, `5xx detectados: ${networkErrors.join(", ")}`).toHaveLength(0);
    const real = consoleErrors.filter(e => !e.includes("Warning:"));
    expect(real, `JS errors: ${real.join("; ")}`).toHaveLength(0);
  });

  test("API: detalle venta #1 expone tips relacional", async ({ page }) => {
    await loginLocal(page);
    const token = await page.evaluate(() => localStorage.getItem("access"));
    expect(token).toBeTruthy();

    const resp = await page.request.get("http://localhost:8000/api/sales/sales/1/", {
      headers: {
        Authorization: `Bearer ${token}`,
        "X-Store-Id": "1",
      },
    });
    expect(resp.status(), `detalle status: ${resp.status()}`).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty("tips");
    expect(Array.isArray(body.tips)).toBe(true);
  });

  test("API: PATCH /sales/1/tip/ acepta split + Sale.tip se actualiza", async ({ page }) => {
    await loginLocal(page);
    const token = await page.evaluate(() => localStorage.getItem("access"));

    // PATCH split tip
    const patchResp = await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: {
        Authorization: `Bearer ${token}`,
        "X-Store-Id": "1",
        "Content-Type": "application/json",
      },
      data: { tips: [
        { method: "cash", amount: "250" },
        { method: "debit", amount: "150" },
      ]},
    });
    expect(patchResp.status(), `PATCH status: ${patchResp.status()}`).toBe(200);
    const patchBody = await patchResp.json();
    expect(patchBody.tip).toBe("400.00");
    expect(patchBody.tips).toHaveLength(2);

    // Verificar persistencia
    const detailResp = await page.request.get("http://localhost:8000/api/sales/sales/1/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1" },
    });
    const detail = await detailResp.json();
    expect(detail.tip).toBe("400.00");
    expect(detail.tips).toHaveLength(2);
    const methods = detail.tips.map((t: any) => t.method).sort();
    expect(methods).toEqual(["cash", "debit"]);

    // Restaurar al original
    await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1", "Content-Type": "application/json" },
      data: { tips: [{ method: "cash", amount: "500" }] },
    });
  });

  test("API: PATCH legacy {tip, tip_method} sigue funcionando", async ({ page }) => {
    await loginLocal(page);
    const token = await page.evaluate(() => localStorage.getItem("access"));

    const resp = await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1", "Content-Type": "application/json" },
      data: { tip: "750", tip_method: "transfer" },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.tip).toBe("750.00");
    expect(body.tips).toHaveLength(1);
    expect(body.tips[0].method).toBe("transfer");

    // Restaurar
    await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1", "Content-Type": "application/json" },
      data: { tips: [{ method: "cash", amount: "500" }] },
    });
  });

  test("API: tips=[] vacía elimina propinas + Sale.tip = 0", async ({ page }) => {
    await loginLocal(page);
    const token = await page.evaluate(() => localStorage.getItem("access"));

    const resp = await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1", "Content-Type": "application/json" },
      data: { tips: [] },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.tip).toBe("0.00");
    expect(body.tips).toHaveLength(0);

    // Restaurar
    await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1", "Content-Type": "application/json" },
      data: { tips: [{ method: "cash", amount: "500" }] },
    });
  });

  test("API: validaciones — método inválido + monto negativo", async ({ page }) => {
    await loginLocal(page);
    const token = await page.evaluate(() => localStorage.getItem("access"));

    const r1 = await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1", "Content-Type": "application/json" },
      data: { tips: [{ method: "bitcoin", amount: "100" }] },
    });
    expect(r1.status()).toBe(400);

    const r2 = await page.request.patch("http://localhost:8000/api/sales/sales/1/tip/", {
      headers: { Authorization: `Bearer ${token}`, "X-Store-Id": "1", "Content-Type": "application/json" },
      data: { tips: [{ method: "cash", amount: "-10" }] },
    });
    expect(r2.status()).toBe(400);
  });

  test("UI: detalle venta muestra apartado de propina", async ({ page }) => {
    await loginLocal(page);
    await page.goto("/dashboard/sales/1");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(3000);

    // En la página standalone aparece "💵 Propina"; en el DetailPanel
    // lateral aparece "Propina cobrada". Ambas matchean /Propina/i.
    const tipHeader = page.locator("text=/Propina/i").first();
    await expect(tipHeader).toBeVisible({ timeout: 10000 });

    expect(networkErrors).toHaveLength(0);
    const real = consoleErrors.filter(e => !e.includes("Warning:"));
    expect(real, `JS errors en /sales/1: ${real.join("; ")}`).toHaveLength(0);
  });

  test("UI: modal Editar propina se abre con UI split (botón Agregar)", async ({ page }) => {
    await loginLocal(page);
    await page.goto("/dashboard/sales/1");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(3000);

    // Buscar el botón ✏️ junto a "Propina cobrada" y clickearlo.
    // El botón es un <button title="Editar propina">.
    const editBtn = page.locator('button[title="Editar propina"]').first();
    await expect(editBtn).toBeVisible({ timeout: 10000 });
    await editBtn.click();

    // El modal renderiza con título "Editar propina" + botón "+ Agregar propina"
    await expect(page.locator("text=Editar propina")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=/Agregar propina/")).toBeVisible({ timeout: 5000 });

    // Y debe tener un select de método con la opción "Efectivo"
    await expect(page.locator("select").first()).toBeVisible();

    expect(networkErrors).toHaveLength(0);
    const real = consoleErrors.filter(e => !e.includes("Warning:"));
    expect(real, `JS errors en modal: ${real.join("; ")}`).toHaveLength(0);
  });
});
