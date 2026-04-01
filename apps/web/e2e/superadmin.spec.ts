import { test, expect } from "@playwright/test";

test.describe("Superadmin", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/superadmin/login");
    await page.evaluate(() => localStorage.clear());
  });

  test("superadmin login page renders", async ({ page }) => {
    await expect(page.getByText("Pulstock Admin")).toBeVisible();
    await expect(page.getByText("Acceder al panel")).toBeVisible();
  });

  test("superadmin login with valid credentials", async ({ page }) => {
    await page.locator('input[type="text"]').fill("daniel@dev.cl");
    await page.locator('input[type="password"]').fill("usk30!SLXL");
    await page.getByText("Acceder al panel").click();

    await page.waitForURL("**/superadmin", { timeout: 10000 });
    await expect(page.getByText("Dashboard")).toBeVisible();
    await expect(page.getByText("MRR")).toBeVisible();
  });

  test("superadmin dashboard shows KPIs", async ({ page }) => {
    // Login
    await page.locator('input[type="text"]').fill("daniel@dev.cl");
    await page.locator('input[type="password"]').fill("usk30!SLXL");
    await page.getByText("Acceder al panel").click();
    await page.waitForURL("**/superadmin", { timeout: 10000 });

    await expect(page.locator("text=TENANTS ACTIVOS").first()).toBeVisible();
    await expect(page.locator("text=USUARIOS").first()).toBeVisible();
  });

  test("forecast IA page shows training logs", async ({ page }) => {
    // Login
    await page.locator('input[type="text"]').fill("daniel@dev.cl");
    await page.locator('input[type="password"]').fill("usk30!SLXL");
    await page.getByText("Acceder al panel").click();
    await page.waitForURL("**/superadmin", { timeout: 10000 });

    // Navigate to Forecast IA
    await page.getByText("Forecast IA").click();
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("Forecast IA — Métricas")).toBeVisible();
    await expect(page.getByText("MODELOS ACTIVOS")).toBeVisible();
    await expect(page.getByText("MAPE PROMEDIO")).toBeVisible();

    // Training logs section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);
    await expect(page.getByText("Historial de entrenamiento")).toBeVisible();
    await expect(page.getByText("Exitoso").first()).toBeVisible();
  });

  test("tenants page shows Marbrava", async ({ page }) => {
    // Login
    await page.locator('input[type="text"]').fill("daniel@dev.cl");
    await page.locator('input[type="password"]').fill("usk30!SLXL");
    await page.getByText("Acceder al panel").click();
    await page.waitForURL("**/superadmin", { timeout: 10000 });

    await page.getByText("Tenants").click();
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("Marbrava")).toBeVisible();
    await expect(page.getByText("Plan Pro")).toBeVisible();
  });
});
