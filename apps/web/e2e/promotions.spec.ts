/**
 * E2E: flujo de Ofertas/Promociones — feature donde Mario detectó el bug
 * de discount_type (07/05/26).
 *
 * Cubre:
 *  - Crear oferta % (pct) — el caso que fallaba antes del fix 03b6c5b
 *  - Crear oferta precio fijo (fixed_price)
 *  - Validación frontend: % > 100 muestra error
 *  - Editar oferta (PATCH) — testea los fixes 3faca95 (discount_type, pct>100)
 *  - Soft-delete (Eliminar pone is_active=False)
 *  - Que la promo aparezca en /api/promotions/active-for-products/
 *
 * Ejecución segura: tenant E2E aislado. afterEach borra todas las promos
 * que se hayan creado, dejando el tenant limpio para la siguiente corrida.
 */
import { test, expect } from "@playwright/test";
import { deleteAllPromotions } from "./_helpers";

const PRODUCT_LATTE_NAME = "Latte E2E";

test.describe("Ofertas (Promociones)", () => {
  test.beforeEach(async ({ page }) => {
    // Autenticación cargada por storageState (global-setup).
    await page.goto("/dashboard/promotions");
    await page.waitForLoadState("networkidle");
  });

  test.afterEach(async ({ page, baseURL }) => {
    // Limpieza: borrar TODAS las promos del tenant E2E así no se ensucia.
    await deleteAllPromotions(page, baseURL!);
  });

  test("crear oferta de % (pct) — el caso del bug discount_type", async ({ page }) => {
    await page.goto("/dashboard/promotions");
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /\+ crear oferta|crear oferta/i }).click();
    await expect(page.getByText(/crear oferta/i).first()).toBeVisible();

    // Llenar nombre
    await page.getByPlaceholder("Ej: Promo Verano 2026").fill("E2E 30% off Latte");

    // El radio "Porcentaje (%)" viene seleccionado por default ahora (post-fix)
    const pctRadio = page.locator('input[type="radio"]').first();
    await expect(pctRadio).toBeChecked();

    // Valor del descuento
    const valueInput = page.locator('input[type="number"]').first();
    await valueInput.fill("30");

    // Fechas (ISO local format)
    const start = new Date(Date.now() - 60_000).toISOString().slice(0, 16);
    const end = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString().slice(0, 16);
    const dateInputs = page.locator('input[type="datetime-local"]');
    await dateInputs.nth(0).fill(start);
    await dateInputs.nth(1).fill(end);

    // Filtrar por SKU para que solo aparezca Latte E2E (evita scroll
    // y ambigüedad cuando hay muchos productos en la lista del modal).
    await page.getByPlaceholder("Buscar por nombre o SKU...").fill("E2E-LATTE");
    // El nombre del producto está envuelto en un div clickeable que llama
    // toggleProduct(). Es más robusto que buscar el checkbox sibling
    // (la estructura del DOM puede cambiar).
    const row = page.getByText(PRODUCT_LATTE_NAME).first();
    await row.waitFor({ state: "visible", timeout: 5000 });
    await row.click();

    // Confirmar — antes esto fallaba con 400 "percentage no es elección válida"
    await page.getByRole("button", { name: /^crear oferta$/i }).click();

    // El modal cierra y aparece toast OK
    await expect(page.getByText(/oferta creada correctamente/i)).toBeVisible({ timeout: 8000 });

    // La oferta aparece en la tabla con label "30% OFF".
    // Hay múltiples matches (tabla con promos viejas soft-deleted +
    // posiblemente el banner del toast) — usamos .first() para evitar
    // strict mode violation.
    await expect(page.getByText("E2E 30% off Latte").first()).toBeVisible();
    await expect(page.getByText(/30% OFF/i).first()).toBeVisible();
  });

  test("crear oferta de precio fijo (fixed_price)", async ({ page }) => {
    await page.goto("/dashboard/promotions");
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /\+ crear oferta|crear oferta/i }).click();
    await page.getByPlaceholder("Ej: Promo Verano 2026").fill("E2E Latte $1500 fijo");

    // Cambiar a "Precio fijo ($)"
    await page.getByText(/precio fijo/i).first().click();

    await page.locator('input[type="number"]').first().fill("1500");

    const start = new Date(Date.now() - 60_000).toISOString().slice(0, 16);
    const end = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString().slice(0, 16);
    const dateInputs = page.locator('input[type="datetime-local"]');
    await dateInputs.nth(0).fill(start);
    await dateInputs.nth(1).fill(end);

    await page.getByPlaceholder("Buscar por nombre o SKU...").fill("E2E-LATTE");
    // El nombre del producto está envuelto en un div clickeable que llama
    // toggleProduct(). Es más robusto que buscar el checkbox sibling
    // (la estructura del DOM puede cambiar).
    const row = page.getByText(PRODUCT_LATTE_NAME).first();
    await row.waitFor({ state: "visible", timeout: 5000 });
    await row.click();

    await page.getByRole("button", { name: /^crear oferta$/i }).click();
    await expect(page.getByText(/oferta creada correctamente/i)).toBeVisible({ timeout: 8000 });
  });

  test("validación frontend: porcentaje > 100 muestra error rojo", async ({ page }) => {
    await page.goto("/dashboard/promotions");
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /\+ crear oferta|crear oferta/i }).click();
    await page.getByPlaceholder("Ej: Promo Verano 2026").fill("Mal porcentaje");
    await page.locator('input[type="number"]').first().fill("150");

    // El frontend muestra el mensaje de validación en rojo
    await expect(page.getByText(/no puede ser mayor a 100/i)).toBeVisible({ timeout: 3000 });
  });

  test("la promo creada aparece en /api/promotions/active-for-products/", async ({ page, baseURL }) => {
    // 1. Crear promo vía API (más rápido que UI)
    const apiURL = baseURL!.replace(/:300\d/, ":8000") + "/api";
    const token = await page.evaluate(() => localStorage.getItem("access"));

    // Buscar product_id del Latte
    const productsRes = await page.request.get(`${apiURL}/catalog/products/?q=Latte E2E`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const products = (await productsRes.json()).results;
    const latteId = products.find((p: any) => p.name === PRODUCT_LATTE_NAME)?.id;
    expect(latteId, "Producto seed 'Latte E2E' no encontrado").toBeTruthy();

    const created = await page.request.post(`${apiURL}/promotions/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: "E2E active check",
        discount_type: "pct",
        discount_value: "25",
        start_date: new Date(Date.now() - 60_000).toISOString(),
        end_date: new Date(Date.now() + 86400000).toISOString(),
        product_items: [{ product_id: latteId, override_discount_value: null }],
      },
    });
    expect(created.status(), `Create falló: ${await created.text()}`).toBe(201);

    // 2. Pedir activas para el producto — debe devolver la nuestra
    const activeRes = await page.request.get(
      `${apiURL}/promotions/active-for-products/?product_ids=${latteId}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(activeRes.status()).toBe(200);
    const activeData = await activeRes.json();
    expect(activeData.results.length).toBeGreaterThanOrEqual(1);

    // El precio promocional es 3000 - 25% = 2250 (Latte E2E está a $3000)
    const ours = activeData.results.find((r: any) => r.promotion_name === "E2E active check");
    expect(ours).toBeTruthy();
    expect(Number(ours.promo_price)).toBe(2250);
    expect(ours.discount_type).toBe("pct");
  });

  test("editar oferta: PATCH valida discount_type inválido (bug 3faca95)", async ({ page, baseURL }) => {
    const apiURL = baseURL!.replace(/:300\d/, ":8000") + "/api";
    const token = await page.evaluate(() => localStorage.getItem("access"));

    // Crear promo válida primero
    const productsRes = await page.request.get(`${apiURL}/catalog/products/?q=Latte E2E`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const latteId = (await productsRes.json()).results.find(
      (p: any) => p.name === PRODUCT_LATTE_NAME,
    )?.id;

    const created = await page.request.post(`${apiURL}/promotions/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: "E2E patch test",
        discount_type: "pct",
        discount_value: "20",
        start_date: new Date(Date.now() - 60_000).toISOString(),
        end_date: new Date(Date.now() + 86400000).toISOString(),
        product_items: [{ product_id: latteId, override_discount_value: null }],
      },
    });
    const promoId = (await created.json()).id;

    // Intentar PATCH con discount_type inválido — DEBE rechazar 400
    const badPatch = await page.request.patch(`${apiURL}/promotions/${promoId}/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { discount_type: "invalid_type" },
    });
    expect(badPatch.status()).toBe(400);

    // Intentar PATCH con pct > 100 — DEBE rechazar 400
    const badPct = await page.request.patch(`${apiURL}/promotions/${promoId}/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { discount_value: "150" },
    });
    expect(badPct.status()).toBe(400);

    // PATCH válido SÍ funciona
    const goodPatch = await page.request.patch(`${apiURL}/promotions/${promoId}/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name: "E2E renombrada" },
    });
    expect(goodPatch.status()).toBe(200);
  });

  test("DELETE soft-deletea (is_active=False) en vez de borrar", async ({ page, baseURL }) => {
    const apiURL = baseURL!.replace(/:300\d/, ":8000") + "/api";
    const token = await page.evaluate(() => localStorage.getItem("access"));

    const productsRes = await page.request.get(`${apiURL}/catalog/products/?q=Latte E2E`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const latteId = (await productsRes.json()).results.find(
      (p: any) => p.name === PRODUCT_LATTE_NAME,
    )?.id;

    const created = await page.request.post(`${apiURL}/promotions/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: "E2E delete test",
        discount_type: "pct",
        discount_value: "10",
        start_date: new Date(Date.now() - 60_000).toISOString(),
        end_date: new Date(Date.now() + 86400000).toISOString(),
        product_items: [{ product_id: latteId, override_discount_value: null }],
      },
    });
    const promoId = (await created.json()).id;

    // DELETE
    const del = await page.request.delete(`${apiURL}/promotions/${promoId}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(del.status()).toBe(204);

    // El registro EXISTE pero is_active=False
    const detail = await page.request.get(`${apiURL}/promotions/${promoId}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(detail.status()).toBe(200);
    const data = await detail.json();
    expect(data.is_active).toBe(false);
  });
});
