/**
 * E2E: visibilidad del sidebar después de los cambios del 07/05/26.
 *
 * Lo que probamos:
 *  - Items que DEBEN aparecer en el sidebar para owner: Precios, Ofertas
 *  - Items que NO deben aparecer (Mario los pidió ocultos porque ya se
 *    acceden desde Caja): Propinas, Movimientos, Categorías
 *  - Las rutas ocultas siguen siendo accesibles directamente por URL
 *
 * Bugs que prevendría una regresión acá:
 *   - Que vuelva a aparecer "Propinas" como entrada propia
 *   - Que se rompa el menú "Ofertas" (icono o link)
 *   - Que alguien edite el Sidebar.tsx muerto en vez de layout.tsx
 */
import { test, expect } from "@playwright/test";

test.describe("Sidebar visibility — owner role", () => {
  test.beforeEach(async ({ page }) => {
    // storageState (de global-setup) ya nos deja autenticados.
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
  });

  test("muestra los items que SI deben aparecer", async ({ page }) => {
    const aside = page.locator("aside, nav").first();
    // Items principales — todos visibles para owner
    for (const label of [
      "Dashboard",
      "Catálogo",
      "Recetas",
      "Precios",
      "Punto de Venta",
      "Ventas",
      "Ofertas",     // ← el item que Mario buscaba
      "Caja",
      "Mesas",
      "Compras",
      "Stock",
      "Kardex",
      "Salidas",
      "Reportes",
      "Predicción",
      "Configuración",
    ]) {
      const link = aside.getByRole("link", { name: label, exact: false }).first();
      await expect(link, `Esperaba ver "${label}" en el sidebar`).toBeVisible({ timeout: 10000 });
    }
  });

  test("oculta Propinas, Movimientos y Categorías (se acceden desde Caja)", async ({ page }) => {
    // Estos NO deben aparecer como entradas propias del menú.
    // Si vuelven, el commit 628ae4d se rompió.
    const aside = page.locator("aside").first();

    for (const hidden of ["Propinas", "Movimientos", "Categorías"]) {
      // Buscamos un link de NIVEL del menú principal, no contenido random.
      const link = aside.getByRole("link", { name: new RegExp(`^${hidden}$`) });
      await expect(
        link,
        `"${hidden}" NO debería estar como entrada del sidebar (se accede desde Caja)`,
      ).toHaveCount(0);
    }
  });

  test("las rutas ocultas siguen siendo navegables directamente", async ({ page }) => {
    // Aunque no estén en el sidebar, las páginas tienen que responder.
    for (const path of [
      "/dashboard/propinas",
      "/dashboard/caja/movimientos",
      "/dashboard/caja/categorias",
    ]) {
      await page.goto(path);
      await page.waitForLoadState("domcontentloaded");
      await expect(page).toHaveURL(new RegExp(path));
      // Tiene que NO haber un error de "no encontrado"
      await expect(page.getByText(/404|not.found|no encontrad/i)).toHaveCount(0);
    }
  });

  test("el item Ofertas tiene su icono dedicado (no el de $)", async ({ page }) => {
    // El icono "offers" es un path de etiqueta de descuento (M20.59 13.41...).
    // Si se usa el de "sales" ($), Mario lo confunde con Ventas (commit 4846d46).
    const aside = page.locator("aside").first();
    const ofertasLink = aside.getByRole("link", { name: "Ofertas" });

    // El icono es un SVG dentro del link
    const svg = ofertasLink.locator("svg").first();
    await expect(svg).toBeVisible();

    // Buscamos el path característico del icono "offers" (etiqueta).
    // El SVG de "sales" usa <line x1="12" y1="1" x2="12" y2="23"/>
    // El SVG de "offers" tiene un <path d="M20.59 13.41 ...">
    const tagPath = svg.locator('path[d^="M20.59 13.41"]');
    await expect(
      tagPath,
      "Ofertas debe usar el icono 'offers' (etiqueta), no 'sales' ($)",
    ).toHaveCount(1);
  });
});
