import { test, expect } from "@playwright/test";
import { loginAsUser } from "./helpers";

test.describe("Settings - Usuarios", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await page.goto("/dashboard/settings");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);
  });

  test("settings page loads with tabs", async ({ page }) => {
    await expect(page.locator("main").getByText("Configuración").first()).toBeVisible();
    await expect(page.locator("main button").filter({ hasText: "Usuarios" }).first()).toBeVisible();
  });

  test("usuarios tab shows user list", async ({ page }) => {
    await page.locator("main button").filter({ hasText: "Usuarios" }).first().click();
    await page.waitForTimeout(2000);
    await expect(page.locator("text=mario@marbrava.cl").first()).toBeVisible();
  });

  test("editing user and typing password shows confirmation field", async ({ page }) => {
    await page.locator("main button").filter({ hasText: "Usuarios" }).first().click();
    await page.waitForTimeout(2000);

    // Click first "Editar" button
    await page.locator("button").filter({ hasText: "Editar" }).first().click();
    await page.waitForTimeout(500);

    // Type in password field
    await page.getByPlaceholder("Dejar vacío para no cambiar").fill("newpassword123");
    await page.waitForTimeout(500);

    // Confirmation field should appear
    await expect(page.locator("text=contraseña actual").first()).toBeVisible();
  });
});
