# Pulstock

SaaS de inventario y punto de venta para el mercado chileno. Multi-tenant, con
un motor de pronóstico de demanda que sugiere qué comprar y cuánto.

Cliente en producción: **Café Marbrava** (Santiago). Locale `es-CL`, moneda CLP,
IVA 19%, zona horaria America/Santiago. **Toda la interfaz está en español.**

---

## Qué hace, en una frase

Registra las ventas en el punto de venta, descuenta el stock según las recetas,
aprende cuánto se vende de cada cosa y avisa qué falta comprar antes de que se
acabe.

Lo que lo diferencia de un POS común es el **pronóstico por ingrediente**: no
predice cuántos lattes se van a vender, predice cuántos mililitros de leche van a
hacer falta —sumando lo que consume cada plato que la lleva—. En el tier
latinoamericano casi ningún competidor tiene forecast propio.

---

## Arranque rápido

Hacen falta **Python 3.12** y **Node 22** (son las versiones que corre CI).

```bash
# Backend
cd apps/api
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r ../requirements.txt
cp .env.example .env                               # editar DJANGO_SECRET_KEY
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

```bash
# Frontend, en otra terminal
cd apps/web
npm install
cp .env.example .env.local                         # NEXT_PUBLIC_API_URL
npm run dev
```

La aplicación queda en `http://localhost:3000` y la API en
`http://localhost:8000/api`.

En desarrollo la base es SQLite; en producción, PostgreSQL vía `DATABASE_URL`.

## Tests

```bash
cd apps/api && pytest           # ~2100 tests
cd apps/web && npm run test:run  # ~230 tests
```

`pytest.ini` tiene `--maxfail=1`: la suite se detiene en el primer fallo.

Cuatro tests de concurrencia se saltan fuera de PostgreSQL — usan
`select_for_update`, que SQLite no soporta.

---

## Cómo está organizado

```
apps/api/     Django 5.1 + DRF
apps/web/     Next.js 15 (App Router) + React 19 + TypeScript
tools/        Agente de impresión que corre en el PC del local
docs/         Documentación (ver abajo)
nginx/        Configuración del proxy en producción
```

### Aplicaciones del backend

| App | De qué se ocupa |
|---|---|
| `core` | Tenant, User, Warehouse, permisos |
| `catalog` | Productos, categorías, unidades, códigos de barra |
| `inventory` | Stock, costo promedio ponderado, kardex, mínimos |
| `sales` | Ventas y líneas de venta |
| `purchases` | Órdenes de compra y proveedores |
| `caja` | Apertura, cierre y arqueo de caja |
| `tables` | Mesas y comandas |
| `forecast` | Pronóstico de demanda y sugerencias de compra |
| `billing` | Suscripciones y pasarela de pago (Flow.cl) |
| `printing` | Impresión en la nube hacia el agente local |
| `reports`, `dashboard` | Analítica |
| `superadmin` | Administración de la plataforma |

---

## Lo que hay que leer antes de tocar

Estos documentos evitan re-deducir cosas que ya costaron caro:

| Documento | Cuándo consultarlo |
|---|---|
| **[docs/ops/](docs/ops/)** | Antes de tocar producción. Acceso, deploys, logs, backups, emergencias. Verificado comando por comando contra el servidor. |
| **[FORMULAS.md](FORMULAS.md)** | Cualquier cosa que toque plata: costeo, márgenes, IVA, valorización de stock. |
| **[FORECAST_ENGINE.md](FORECAST_ENGINE.md)** | Cómo funciona el motor de pronóstico. |
| **[MODULES_AUDIT.md](MODULES_AUDIT.md)** | Auditoría módulo a módulo con archivo:línea. Bugs conocidos. |
| **[UX_AUDIT.md](UX_AUDIT.md)** | Deuda de interfaz, pantalla por pantalla. |
| **[SAAS_RESEARCH.md](SAAS_RESEARCH.md)** | Comparación contra la competencia, brechas, normativa chilena. |
| **[FORECAST_RESEARCH.md](FORECAST_RESEARCH.md)** | Estado del arte en pronóstico de inventario. |
| **[CLAUDE.md](CLAUDE.md)** | Convenciones del código. Escrito para asistentes de IA, útil para humanos. |
| **[docs/manual-venta-modelo-predictivo.md](docs/manual-venta-modelo-predictivo.md)** | Cómo explicar y vender el motor de pronóstico. Con los números reales medidos, no con los que quedarían mejor. |
| **[docs/manual-de-uso.md](docs/manual-de-uso.md)** | Qué hace cada pantalla y para quién. Escrito recorriendo la instalación real. |
| **[docs/traspaso-cuentas.md](docs/traspaso-cuentas.md)** | Qué servicios sostienen el sistema, a nombre de quién, y el estado frente a la Ley 21.719. |
| **[docs/expediente-legal.md](docs/expediente-legal.md)** | Los hechos verificados para que un abogado redacte los ToS. El más urgente: hoy no existe ningún contrato con el cliente. |

---

## Tres cosas que sorprenden

**1. Multi-tenancy a mano.** Cada consulta filtra por `tenant`. No hay un
middleware que lo garantice: si escribes una consulta sin `.filter(tenant=...)`,
expone datos de otro negocio. Es la regla más importante del código.

**2. El local activo es `user.active_store`, no un header.** Existe un
`StoreContextMiddleware` que lee `X-Store-Id`, pero **nunca se instaló** — es
código muerto. Cablear ese header para un módulo dejaría los reportes viendo un
local distinto que las ventas.

**3. En producción no corre Celery.** Todo el trabajo periódico son management
commands invocados por cron. La configuración de Celery existe pero no se usa.
Ver [docs/ops/pulstock-crontab.txt](docs/ops/pulstock-crontab.txt).

---

## Producción

Un solo servidor Hetzner con Nginx, Gunicorn, PM2 y PostgreSQL. **No hay
Vercel**: el frontend se despliega compilándolo en el servidor, así que un
`git pull` sin `next build` no actualiza nada.

El procedimiento completo está en [docs/ops/04-deploy.md](docs/ops/04-deploy.md).
El `deploy.sh` de la raíz es un resto de una configuración vieja y **no se
usa**: el script real vive en el servidor, en `~/deploy.sh`.

CI (GitHub Actions) corre los tests del backend y compila el frontend en cada PR.
**No despliega nada**: el deploy es manual.
