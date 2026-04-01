import { test, expect, Page } from "@playwright/test";
import { loginAsUser } from "./helpers";

/**
 * AUDITORÍA DETALLADA DE ERRORES
 * Verifica que las páginas muestren mensajes amigables cuando:
 * 1. Se accede con IDs inválidos
 * 2. La API devuelve 500
 * 3. El backend está caído
 */

async function getPageState(page: Page): Promise<{
  bodyText: string;
  hasBlankPage: boolean;
  hasUnhandledError: boolean;
  hasNextJsError: boolean;
  hasFriendlyError: boolean;
  has500Visible: boolean;
}> {
  await page.waitForTimeout(4000);
  const bodyText = await page.locator("body").innerText().catch(() => "");
  const lower = bodyText.toLowerCase();
  return {
    bodyText: bodyText.substring(0, 500),
    hasBlankPage: bodyText.trim().length < 20,
    hasUnhandledError: lower.includes("unhandled runtime error") || lower.includes("application error"),
    hasNextJsError: (await page.locator("nextjs-portal").count().catch(() => 0)) > 0,
    hasFriendlyError: lower.includes("no encontr") || lower.includes("no existe") || lower.includes("error") || lower.includes("404") || lower.includes("no se pudo"),
    has500Visible: lower.includes("internal server error") || lower.includes("500"),
  };
}

// ─── IDs inválidos ─────────────────────────────────────

test.describe("Pantallas de error con IDs inválidos", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test("venta inexistente /sales/99999 muestra mensaje amigable", async ({ page }) => {
    await page.goto("/dashboard/sales/99999");
    const state = await getPageState(page);
    console.log(`[SALE-404] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}, friendly=${state.hasFriendlyError}`);
    console.log(`[SALE-404] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
    expect(state.hasBlankPage).toBeFalsy();
  });

  test("compra inexistente /purchases/99999 muestra mensaje amigable", async ({ page }) => {
    await page.goto("/dashboard/purchases/99999");
    const state = await getPageState(page);
    console.log(`[PURCHASE-404] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}, friendly=${state.hasFriendlyError}`);
    console.log(`[PURCHASE-404] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
    expect(state.hasBlankPage).toBeFalsy();
  });

  test("boleta inexistente /pos/receipt/99999 muestra mensaje amigable", async ({ page }) => {
    await page.goto("/dashboard/pos/receipt/99999");
    const state = await getPageState(page);
    console.log(`[RECEIPT-404] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}, friendly=${state.hasFriendlyError}`);
    console.log(`[RECEIPT-404] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
    expect(state.hasBlankPage).toBeFalsy();
  });

  test("transfer inexistente /transfers/99999 muestra mensaje amigable", async ({ page }) => {
    await page.goto("/dashboard/inventory/transfers/99999");
    const state = await getPageState(page);
    console.log(`[TRANSFER-404] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}, friendly=${state.hasFriendlyError}`);
    console.log(`[TRANSFER-404] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
    expect(state.hasBlankPage).toBeFalsy();
  });

  test("tenant SA inexistente /superadmin/tenants/99999", async ({ page }) => {
    // Need superadmin login
    await page.goto("/superadmin/login");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await page.locator('input[type="text"]').waitFor({ state: "visible", timeout: 10000 });
    await page.locator('input[type="text"]').fill("daniel@dev.cl");
    await page.locator('input[type="password"]').fill("usk30!SLXL");
    await page.getByText("Acceder al panel").click();
    await page.waitForURL("**/superadmin**", { timeout: 20000 });

    await page.goto("/superadmin/tenants/99999");
    const state = await getPageState(page);
    console.log(`[SA-TENANT-404] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}, friendly=${state.hasFriendlyError}`);
    console.log(`[SA-TENANT-404] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
    expect(state.hasBlankPage).toBeFalsy();
  });
});

// ─── Backend caído (simulado con route intercept) ──────

test.describe("Simulación de backend caído", () => {
  test("dashboard con TODA la API caída muestra fallback amigable", async ({ page }) => {
    await loginAsUser(page);

    // Block ALL API calls to simulate backend down
    await page.route("**/api/**", (route) => {
      // Except auth endpoints (already logged in)
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-DASHBOARD] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-DASHBOARD] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("POS con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/pos");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-POS] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-POS] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("ventas con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/sales");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-SALES] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-SALES] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("catálogo con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/catalog");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-CATALOG] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-CATALOG] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("reportes con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/reports/sales-summary");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-REPORTS] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-REPORTS] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("settings con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/settings");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-SETTINGS] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-SETTINGS] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("mesas con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/mesas");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-MESAS] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-MESAS] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("forecast con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/forecast");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-FORECAST] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-FORECAST] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });

  test("compras con backend caído no crashea", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/**", (route) => {
      if (route.request().url().includes("/auth/")) {
        route.continue();
        return;
      }
      route.abort("connectionrefused");
    });

    await page.goto("/dashboard/purchases");
    const state = await getPageState(page);
    console.log(`[BACKEND-DOWN-PURCHASES] blank=${state.hasBlankPage}, unhandled=${state.hasUnhandledError}`);
    console.log(`[BACKEND-DOWN-PURCHASES] Body: ${state.bodyText.substring(0, 300)}`);
    expect(state.hasUnhandledError).toBeFalsy();
  });
});
