import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await page.getByPlaceholder("Tu nombre de usuario").waitFor({ state: "visible", timeout: 15000 });
  });

  test("login page renders correctly", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Pulstock" })).toBeVisible();
    await expect(page.getByPlaceholder("Tu nombre de usuario")).toBeVisible();
    await expect(page.getByRole("button", { name: "Ingresar" })).toBeVisible();
  });

  test("login with valid credentials redirects to dashboard", async ({ page }) => {
    await page.getByPlaceholder("Tu nombre de usuario").fill("mario@marbrava.cl");
    await page.locator('input[type="password"]').fill("marbravadennis745");
    await page.getByRole("button", { name: "Ingresar" }).click();

    await page.waitForURL("**/dashboard**", { timeout: 20000 });
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("login with invalid credentials shows error", async ({ page }) => {
    await page.getByPlaceholder("Tu nombre de usuario").fill("bad@user.cl");
    await page.locator('input[type="password"]').fill("wrongpassword");
    await page.getByRole("button", { name: "Ingresar" }).click();

    await expect(page.getByText(/incorrectos|Error/i)).toBeVisible({ timeout: 5000 });
  });

  test("login page does NOT auto-redirect with stale token", async ({ page }) => {
    await page.goto("/login");
    await page.evaluate(() => localStorage.setItem("access", "stale-token"));
    await page.goto("/login");

    // Should still show the login form
    await expect(page.getByPlaceholder("Tu nombre de usuario")).toBeVisible();
  });
});
