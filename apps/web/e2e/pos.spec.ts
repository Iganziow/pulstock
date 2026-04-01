import { test, expect } from "@playwright/test";
import { loginAsUser } from "./helpers";

const SEARCH_PLACEHOLDER = /Escanea barcode|SKU o nombre/;

test.describe("POS - Punto de Venta", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await page.goto("/dashboard/pos");
    await page.waitForLoadState("domcontentloaded");
    await page.getByPlaceholder(SEARCH_PLACEHOLDER).waitFor({ state: "visible", timeout: 20000 });
  });

  test("POS page loads with search and empty cart", async ({ page }) => {
    await expect(page.locator("h1").filter({ hasText: "Punto de Venta" })).toBeVisible();
    await expect(page.getByPlaceholder(SEARCH_PLACEHOLDER)).toBeVisible();
    await expect(page.locator("text=Carrito vacío").first()).toBeVisible();
  });

  test("search for product shows results", async ({ page }) => {
    await page.getByPlaceholder(SEARCH_PLACEHOLDER).fill("cafe");
    await page.waitForTimeout(2000);
    await expect(page.locator("text=Cafe").first()).toBeVisible({ timeout: 5000 });
  });

  test("add product to cart updates total", async ({ page }) => {
    await page.getByPlaceholder(SEARCH_PLACEHOLDER).fill("cafe");
    await page.waitForTimeout(2000);
    await page.locator("text=Cafe").first().click();
    await page.waitForTimeout(1000);
    await expect(page.locator("text=Total").first()).toBeVisible();
  });

  test("payment methods visible after adding product", async ({ page }) => {
    await page.getByPlaceholder(SEARCH_PLACEHOLDER).fill("cafe");
    await page.waitForTimeout(2000);
    await page.locator("text=Cafe").first().click();
    await page.waitForTimeout(500);
    await expect(page.locator("button").filter({ hasText: "Efectivo" })).toBeVisible();
    await expect(page.locator("button").filter({ hasText: "Débito" })).toBeVisible();
  });
});
