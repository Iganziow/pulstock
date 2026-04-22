# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Pulstock** — Multi-tenant inventory management SaaS (Chilean market: Spanish locale `es-cl`, CLP currency, America/Santiago timezone, 19% IVA) with a Django REST API backend and Next.js 15 frontend in a monorepo structure. All UI strings are in Spanish.

## Commands

### Backend (`apps/api/`)
```bash
python manage.py runserver 0.0.0.0:8000   # Dev server (port 8000)
python manage.py migrate                   # Apply migrations
python manage.py makemigrations <app>      # Create new migration
python manage.py createsuperuser           # Create admin user
pytest                                     # Run all tests (stops on first failure)
pytest tests/test_<module>.py             # Run single test file
pytest -k "test_name"                     # Run specific test
```

### Frontend (`apps/web/`)
```bash
npm run dev          # Dev server (port 3000)
npm run build        # Production build
npm run lint         # ESLint check
npm run test         # Vitest in watch mode
npm run test:run     # Vitest single pass
npm run test:e2e     # Playwright E2E tests
npm run test:coverage # Vitest with coverage
```

### Celery (`apps/api/`)
```bash
celery -A api worker -l info   # Task worker
celery -A api beat -l info     # Periodic scheduler (billing renewals, trial expiry, payment retries)
```

## Architecture

### Backend (`apps/api/`)
Django 5.1 + DRF with these local apps:

- **`core/`** — Tenant, User (with roles: OWNER/MANAGER/CASHIER/INVENTORY), Warehouse models; custom permissions (`HasTenant`, `IsOwner`, `IsManager`, `IsInventoryOrManager`, `IsManagerOrReadOnly`, `IsSuperAdmin`)
- **`catalog/`** — Product, Category, Unit, Barcode models
- **`inventory/`** — StockItem with weighted average cost tracking; stock movement transactions
- **`sales/`** — Sale orders and SaleLine with cost-at-time-of-sale snapshot
- **`purchases/`** — PurchaseOrder, PurchaseLine, Supplier; drives cost updates
- **`stores/`** — Multi-store management; store context middleware injects current store into requests
- **`caja/`** — Cash register / POS operations
- **`tables/`** — Restaurant table management
- **`reports/`** — Analytics views; uses Pandas for aggregations
- **`forecast/`** — Demand forecasting using statsmodels (with WMA fallback)
- **`billing/`** — Subscription management + Flow.cl payment gateway integration
- **`onboarding/`** — Tenant creation and user signup workflows
- **`dashboard/`** — KPI aggregation views
- **`promotions/`** — Promotional pricing and discount rules
- **`printing/`** — Cloud printing: pairs PC-side `pulstock-agent` to local receipt printers; routes print jobs from any device to the agent (see `tools/pulstock-agent/`)
- **`superadmin/`** — Platform-level admin views (separate from Django admin)

**Auth:** Cookie-based JWT flow. Access token returned in JSON body + httpOnly cookie; refresh token in httpOnly cookie only (path `/api/auth/`). `JWTCookieMiddleware` injects cookie into Authorization header if not present. Token lifetime: 1h access, 7d refresh with rotation and blacklisting.

**Middleware order** (relevant for debugging): `RequestIDMiddleware` → SecurityMiddleware → WhiteNoiseMiddleware → SessionMiddleware → CorsMiddleware → CommonMiddleware → CsrfViewMiddleware → AuthenticationMiddleware → `JWTCookieMiddleware` → `SubscriptionAccessMiddleware` → MessageMiddleware → XFrameOptionsMiddleware.

**Subscription middleware:** `SubscriptionAccessMiddleware` returns 402 for non-paying tenants. Always-allowed routes: `/api/auth/*`, `/api/billing/*`, `/api/core/health/`, `/admin/`.

**Multi-tenancy:** Every model filters by `tenant_id`. All queryset operations must include `.filter(tenant=request.user.tenant)`.

**Pagination:** Page-number based, 50 items/page default (configured in `settings.py`).

**Database:** SQLite in development (`db.sqlite3`), PostgreSQL in production via `DATABASE_URL`.

### Frontend (`apps/web/`)
Next.js 15 App Router + React 19 + TypeScript + Tailwind CSS:

- **`app/(auth)/`** — Login/signup pages (no auth required)
- **`app/(dashboard)/`** — All protected pages; layout wraps with Sidebar + Topbar
- **`app/(superadmin)/`** — Platform admin pages (separate login/layout)
- **`app/checkout/`** — Billing/payment flow (outside dashboard layout)
- **`app/agent/`** — Public landing page to download the Pulstock Printer Agent installer
- **`app/trial/`** — Public trial signup landing
- **`components/`** — Shared UI components (Sidebar, Topbar, ExportButtons, etc.)
- **`lib/`** — `apiFetch` utility with automatic JWT refresh + deduplication; token storage helpers

**API base URL:** `NEXT_PUBLIC_API_URL=http://localhost:8000/api` (from `.env.local`)

**`apiFetch`** (`lib/api.ts`) handles 401 → refresh (POST to `/api/auth/token/refresh/` with cookie) → retry automatically. Uses `credentials: "include"` for CORS. Throws custom `ApiError` with status and data. `apiUpload` handles FormData with the same auto-refresh. Do not implement custom token refresh logic elsewhere.

**Token storage:** Access token in localStorage (for Authorization header); refresh token in httpOnly cookie only. Superadmin flag in localStorage. Helpers: `getAccessToken()`, `setTokens()`, `clearTokens()`, `decodeTokenPayload()`.

## Key Patterns

**Store context:** Sales, inventory, and purchases are scoped to a `store`. The `StoreContextMiddleware` reads `X-Store-Id` header (falls back to `user.active_store`). Views must respect store scoping.

**Cost tracking:** Inventory uses weighted average cost (PPP). When purchases are received, `avg_cost` on `StockItem` is recalculated. `SaleLine` records `cost` at sale time for margin reporting. See `FORMULAS.md` for all costing rules.

**Decimal precision:** Financial fields use `DecimalField` with 12–14 max digits and 2–3 decimal places. Never use floats for money.

**Payment gateway:** `billing/gateway.py` abstracts payment processing. Uses `PAYMENT_GATEWAY` env var (`mock` for dev, `flow` for production Flow.cl). Flow uses HMAC-SHA256 signing.

**Rate limiting:** Login 10/min, registration 10/hr, authenticated 2000/hr, anon 200/hr, sensitive actions 20/hr.

**Design tokens:** `lib/theme.ts` exports `C` — the centralized color palette, border radii, and shadows. Import `C` instead of hardcoding style values. Font: DM Sans, monospace: JetBrains Mono. Accent: `#4F46E5` (indigo).

**Sale idempotency:** Sales accept an `idempotency_key` (unique per tenant) to prevent duplicate submissions. On IntegrityError from key collision, the existing sale is returned instead of creating a new one.

**Exception handler:** Custom DRF handler (`api/exception_handler.py`) converts exceptions to JSON with Spanish messages. IntegrityError → 409 Conflict.

**TypeScript config:** `strict: false`, path alias `@/*` maps to project root.

## Testing

**Backend:** Tests live in `apps/api/tests/`. Pytest config is in `apps/api/pytest.ini` (sets `DJANGO_SETTINGS_MODULE=api.settings`, `--maxfail=1`). All pytest commands must be run from `apps/api/`. Key fixtures from `conftest.py`: `api_client`, `auth_client`, `tenant`, `store`, `user`, `warehouse_a`, `warehouse_b`, `category`, `product`, `stockitem_a`.

**Frontend:** Vitest for unit/component tests, Playwright for E2E. Run from `apps/web/`.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on push to `main` and PRs: backend pytest + frontend typecheck & build. Python 3.12, Node 22.

## Docker (Production)

`docker-compose.yml` at root defines: PostgreSQL 16, Redis 7, Django (Gunicorn, 3 workers), Celery worker + beat, Nginx, Certbot. Dev uses SQLite + `runserver` instead.

## Environment Setup

**Backend `.env` (in `apps/api/`):** see `.env.example` for all variables.
```
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=<secret>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
WEB_ORIGIN=http://localhost:3000
PAYMENT_GATEWAY=mock
```

**Frontend `.env.local` (in `apps/web/`):** see `.env.example`.
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

## Other Repository Components

- **`tools/pulstock-agent/`** — Standalone Python agent that runs on the customer's local PC to bridge cloud print jobs to USB/system/LAN printers. PyInstaller builds a Windows `.exe`. Pairs with the `printing/` backend app via a one-time code from Configuración → Impresoras.
- **`docs/ops/`** — Production operations playbook (server access, deploys, logs, backups, common errors, emergencies, monitoring/Brevo setup). Consult before touching production infra.
- **`FORMULAS.md`** — Authoritative source for all costing/margin/IVA/stock-value formulas. Reference this rather than re-deriving.
- **`FORECAST_ENGINE.md`** — Demand forecasting design (statsmodels + WMA fallback) used by `forecast/`.
- **`DEPLOY.md`** — Deploy procedure (root-level companion to `docs/ops/04-deploy.md`).
