import { Page } from "@playwright/test";

export async function loginAsUser(page: Page) {
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  await page.getByPlaceholder("Tu nombre de usuario").waitFor({ state: "visible", timeout: 15000 });
  await page.getByPlaceholder("Tu nombre de usuario").fill("mario@marbrava.cl");
  await page.locator('input[type="password"]').fill("marbravadennis745");
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForURL("**/dashboard**", { timeout: 25000 });
  await page.waitForLoadState("domcontentloaded");
}

export async function loginAsSuperadmin(page: Page) {
  await page.goto("/superadmin/login");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForLoadState("domcontentloaded");
  await page.locator('input[type="text"]').waitFor({ state: "visible", timeout: 10000 });
  await page.locator('input[type="text"]').fill("daniel@dev.cl");
  await page.locator('input[type="password"]').fill("usk30!SLXL");
  await page.getByText("Acceder al panel").click();
  await page.waitForURL("**/superadmin**", { timeout: 20000 });
  await page.waitForLoadState("networkidle");
}
