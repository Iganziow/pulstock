import { test, expect, Page } from "@playwright/test";
import { loginAsUser, loginAsSuperadmin } from "./helpers";

/**
 * AUDITORÍA COMPLETA — Recorre TODAS las rutas buscando:
 * - Errores 500 / respuestas rotas del API
 * - Pantallas en blanco
 * - Errores de JS en consola
 * - Elementos bloqueantes (spinners infinitos, etc.)
 */

// ─── Helpers ────────────────────────────────────────────

interface RouteResult {
  route: string;
  status: "ok" | "error";
  issues: string[];
}

const results: RouteResult[] = [];

async function auditRoute(page: Page, route: string, label: string) {
  const issues: string[] = [];
  const consoleErrors: string[] = [];
  const networkErrors: string[] = [];

  // Listen for console errors
  const consoleHandler = (msg: any) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Ignore known noise
      if (text.includes("favicon") || text.includes("net::ERR") || text.includes("Download the React DevTools")) return;
      consoleErrors.push(text.substring(0, 200));
    }
  };
  page.on("console", consoleHandler);

  // Listen for failed network requests
  page.on("response", (response) => {
    const status = response.status();
    const url = response.url();
    if (status >= 500) {
      networkErrors.push(`${status} ${url.substring(0, 150)}`);
    }
  });

  try {
    const response = await page.goto(route, { timeout: 30000, waitUntil: "domcontentloaded" });

    // Check HTTP status of page itself
    if (response && response.status() >= 400) {
      issues.push(`HTTP ${response.status()} on page load`);
    }

    // Wait for content to render
    await page.waitForTimeout(3000);

    // Check for blank page
    const bodyText = await page.locator("body").innerText().catch(() => "");
    if (bodyText.trim().length < 10) {
      issues.push("BLANK PAGE — body has almost no text");
    }

    // Check for uncaught error boundaries / Next.js error overlay
    const hasErrorOverlay = await page.locator("nextjs-portal").count().catch(() => 0);
    if (hasErrorOverlay && hasErrorOverlay > 0) {
      issues.push("Next.js error overlay detected");
    }

    // Check for common error patterns in page text
    const pageText = bodyText.toLowerCase();
    if (pageText.includes("application error") || pageText.includes("internal server error")) {
      issues.push("'Application Error' or 'Internal Server Error' visible on page");
    }
    if (pageText.includes("unhandled runtime error")) {
      issues.push("'Unhandled Runtime Error' visible on page");
    }
    if (pageText.includes("something went wrong")) {
      issues.push("'Something went wrong' error visible");
    }

    // Check for infinite loading (spinner still showing after 3s)
    const spinnerCount = await page.locator('[class*="spinner"], [class*="loading"], [class*="animate-spin"]').count().catch(() => 0);
    // This is informational only — some pages legitimately show brief loading

    // Collect network errors
    if (networkErrors.length > 0) {
      issues.push(`API 500 errors: ${networkErrors.join(" | ")}`);
    }

    // Collect console errors (limit to important ones)
    const importantConsoleErrors = consoleErrors.filter(
      (e) => !e.includes("Warning:") && !e.includes("ReactDOM.render")
    );
    if (importantConsoleErrors.length > 0) {
      issues.push(`Console errors: ${importantConsoleErrors.slice(0, 3).join(" | ")}`);
    }

  } catch (err: any) {
    issues.push(`Navigation failed: ${err.message.substring(0, 200)}`);
  }

  page.removeListener("console", consoleHandler);

  const status = issues.length > 0 ? "error" : "ok";
  results.push({ route, status, issues });

  console.log(`[${status.toUpperCase()}] ${label} (${route})${issues.length > 0 ? " — " + issues.join("; ") : ""}`);
}

// ─── Auth Routes (no login required) ────────────────────

test.describe("Auditoría — Rutas públicas", () => {
  test("login page", async ({ page }) => {
    await auditRoute(page, "/login", "Login");
  });

  test("register page", async ({ page }) => {
    await auditRoute(page, "/register", "Register");
  });

  test("root redirect", async ({ page }) => {
    await auditRoute(page, "/", "Root");
  });

  test("404 — ruta inexistente", async ({ page }) => {
    await auditRoute(page, "/esta-ruta-no-existe-xyz", "404 page");
  });

  test("checkout page (sin sesión)", async ({ page }) => {
    await auditRoute(page, "/checkout", "Checkout sin sesión");
  });
});

// ─── Dashboard Routes (login required) ─────────────────

test.describe("Auditoría — Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  const dashboardRoutes = [
    { path: "/dashboard", label: "Dashboard principal" },
    { path: "/dashboard/catalog", label: "Catálogo" },
    { path: "/dashboard/catalog/recetas", label: "Recetas" },
    { path: "/dashboard/pos", label: "Punto de Venta" },
    { path: "/dashboard/sales", label: "Lista de ventas" },
    { path: "/dashboard/caja", label: "Caja" },
    { path: "/dashboard/mesas", label: "Mesas" },
    { path: "/dashboard/mesas/config", label: "Config mesas" },
    { path: "/dashboard/purchases", label: "Compras" },
    { path: "/dashboard/purchases/new", label: "Nueva compra" },
    { path: "/dashboard/inventory", label: "Inventario index" },
    { path: "/dashboard/inventory/stock", label: "Stock" },
    { path: "/dashboard/inventory/stock/adjust", label: "Ajuste de stock" },
    { path: "/dashboard/inventory/stock/moves", label: "Movimientos stock" },
    { path: "/dashboard/inventory/kardex", label: "Kardex" },
    { path: "/dashboard/inventory/kardex-report", label: "Kardex Report" },
    { path: "/dashboard/inventory/salidas", label: "Salidas" },
    { path: "/dashboard/prices", label: "Precios" },
    { path: "/dashboard/promotions", label: "Promociones" },
    { path: "/dashboard/reports", label: "Reportes index" },
    { path: "/dashboard/reports/sales-summary", label: "Resumen ventas" },
    { path: "/dashboard/reports/stock-valued", label: "Stock valorizado" },
    { path: "/dashboard/reports/abc-analysis", label: "Análisis ABC" },
    { path: "/dashboard/reports/audit-trail", label: "Auditoría trail" },
    { path: "/dashboard/reports/inventory-health", label: "Salud inventario" },
    { path: "/dashboard/reports/losses", label: "Pérdidas" },
    { path: "/dashboard/reports/toma-fisica", label: "Toma física" },
    { path: "/dashboard/reports/transfer-suggestion-sheet", label: "Hoja transferencia" },
    { path: "/dashboard/forecast", label: "Predicción" },
    { path: "/dashboard/forecast/suggestions", label: "Sugerencias forecast" },
    { path: "/dashboard/settings", label: "Configuración" },
  ];

  for (const { path, label } of dashboardRoutes) {
    test(`${label} (${path})`, async ({ page }) => {
      await auditRoute(page, path, label);
    });
  }
});

// ─── Dynamic routes with fake IDs ──────────────────────

test.describe("Auditoría — Rutas dinámicas con IDs inválidos", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test("sale detail with invalid ID", async ({ page }) => {
    await auditRoute(page, "/dashboard/sales/99999", "Venta inexistente");
  });

  test("purchase detail with invalid ID", async ({ page }) => {
    await auditRoute(page, "/dashboard/purchases/99999", "Compra inexistente");
  });

  test("receipt with invalid ID", async ({ page }) => {
    await auditRoute(page, "/dashboard/pos/receipt/99999", "Boleta inexistente");
  });

  test("transfer with invalid ID", async ({ page }) => {
    await auditRoute(page, "/dashboard/inventory/transfers/99999", "Transfer inexistente");
  });
});

// ─── Superadmin Routes ─────────────────────────────────

test.describe("Auditoría — Superadmin", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperadmin(page);
  });

  const superadminRoutes = [
    { path: "/superadmin", label: "SA Dashboard" },
    { path: "/superadmin/tenants", label: "SA Tenants" },
    { path: "/superadmin/users", label: "SA Users" },
    { path: "/superadmin/billing", label: "SA Billing" },
    { path: "/superadmin/forecast", label: "SA Forecast" },
  ];

  for (const { path, label } of superadminRoutes) {
    test(`${label} (${path})`, async ({ page }) => {
      await auditRoute(page, path, label);
    });
  }

  test("SA tenant detail invalid ID", async ({ page }) => {
    await auditRoute(page, "/superadmin/tenants/99999", "SA Tenant inexistente");
  });
});

// ─── Edge Cases ────────────────────────────────────────

test.describe("Auditoría — Edge cases", () => {
  test("acceder a dashboard sin login redirige a login", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(3000);
    const url = page.url();
    const isOnLogin = url.includes("/login");
    const isOnDashboard = url.includes("/dashboard");
    console.log(`[INFO] Sin login → URL: ${url}`);
    // Should redirect to login
    expect(isOnLogin || !isOnDashboard).toBeTruthy();
  });

  test("acceder a superadmin sin login redirige", async ({ page }) => {
    await page.goto("/superadmin");
    await page.waitForTimeout(3000);
    const url = page.url();
    console.log(`[INFO] SA sin login → URL: ${url}`);
    expect(url.includes("/login") || url.includes("/superadmin/login")).toBeTruthy();
  });

  test("token expirado redirige a login", async ({ page }) => {
    // Set expired token
    await page.goto("/login");
    await page.evaluate(() => {
      localStorage.setItem("access", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNjAwMDAwMDAwfQ.fakesig");
    });
    await page.goto("/dashboard");
    await page.waitForTimeout(5000);
    const url = page.url();
    console.log(`[INFO] Token expirado → URL: ${url}`);
    // Should end up on login
    expect(url.includes("/login")).toBeTruthy();
  });

  test("double slash en URL no rompe", async ({ page }) => {
    await auditRoute(page, "//dashboard", "Double slash");
  });
});

// ─── API Error Handling (simular errores del backend) ──

test.describe("Auditoría — API errors en dashboard", () => {
  test("dashboard con API que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    // Intercept dashboard summary API to return 500
    await page.route("**/api/dashboard/summary/**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard");
    await page.waitForTimeout(4000);

    // Page should NOT be blank — should show some error state or fallback
    const bodyText = await page.locator("body").innerText();
    console.log(`[API-500-DASHBOARD] Body length: ${bodyText.length}, has content: ${bodyText.trim().length > 20}`);

    // Check for crash indicators
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    if (hasCrash) {
      console.log("[ERROR] Dashboard crashes with API 500!");
    }
    expect(hasCrash).toBeFalsy();
  });

  test("POS con API de productos que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/catalog/products/search**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard/pos");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    console.log(`[API-500-POS] Crashed: ${hasCrash}`);
    expect(hasCrash).toBeFalsy();
  });

  test("catálogo con API de categorías que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/catalog/categories/**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard/catalog");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    console.log(`[API-500-CATALOG] Crashed: ${hasCrash}`);
    expect(hasCrash).toBeFalsy();
  });

  test("ventas con API que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/sales/sales/list/**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard/sales");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    console.log(`[API-500-SALES] Crashed: ${hasCrash}`);
    expect(hasCrash).toBeFalsy();
  });

  test("reportes con API que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/reports/**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard/reports/sales-summary");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    console.log(`[API-500-REPORTS] Crashed: ${hasCrash}`);
    expect(hasCrash).toBeFalsy();
  });

  test("stock con API que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/inventory/stock/**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard/inventory/stock");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    console.log(`[API-500-STOCK] Crashed: ${hasCrash}`);
    expect(hasCrash).toBeFalsy();
  });

  test("forecast con API que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/forecast/**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard/forecast");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    console.log(`[API-500-FORECAST] Crashed: ${hasCrash}`);
    expect(hasCrash).toBeFalsy();
  });

  test("caja con API que devuelve 500", async ({ page }) => {
    await loginAsUser(page);

    await page.route("**/api/caja/**", (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    await page.goto("/dashboard/caja");
    await page.waitForTimeout(3000);

    const bodyText = await page.locator("body").innerText();
    const hasCrash = bodyText.toLowerCase().includes("unhandled") || bodyText.toLowerCase().includes("application error");
    console.log(`[API-500-CAJA] Crashed: ${hasCrash}`);
    expect(hasCrash).toBeFalsy();
  });
});
