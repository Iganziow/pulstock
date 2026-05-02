# Guía de despliegue — Pulstock

**Arquitectura actual:**
- **Todo en un servidor Hetzner** (`65.108.148.200`, dominio `pulstock.cl`)
  - Frontend Next.js → corre como proceso Node bajo PM2 (`pulstock-web`, puerto 3000)
  - Backend Django → Gunicorn (3 workers) sirviendo `/api/`
  - Celery worker + beat → tareas programadas (renewals de billing, forecasts diarios, etc.)
  - PostgreSQL + Redis (locales en el servidor)
  - Nginx → reverse proxy + SSL (Let's Encrypt) → proxy a `pulstock-web` y a Gunicorn
- **NO usamos Vercel** (lo migramos a Hetzner para tener todo en un solo lugar)
- DNS: `dnsmisitio.net` → `pulstock.cl` y `www.pulstock.cl` apuntan a la IP del servidor

---

## Deploy de cambios (procedimiento normal)

Después de pushear a `main`, conectarse al servidor y correr el alias correspondiente:

```bash
ssh ignacio@65.108.148.200
pdeploy           # deploy completo (api + web)
# o más rápido si sólo cambió uno:
pdeploy-api       # solo backend (~10 s)
pdeploy-web       # solo frontend (~1-2 min por el next build)
```

> El detalle completo del script (`~/deploy.sh`) y troubleshooting está en
> [`docs/ops/04-deploy.md`](docs/ops/04-deploy.md). Lee ese archivo si algo falla.

`pdeploy` hace en orden:
1. Asegura ownership del repo a `ignacio`.
2. `git pull origin main` (auto-checkout a main si estabas en otra rama).
3. Recrea el merge migration local `0018_merge_*.py` (ver "migraciones huérfanas" en `04-deploy.md`).
4. **Backend**: `migrate` + `sudo kill -HUP` al gunicorn master (workers se reciclan sin downtime).
5. **Frontend**: `next build` + `sudo pm2 stop pulstock-web` + `sudo pkill -KILL -f next-server` + `sudo pm2 start pulstock-web`.
6. Verificación final con curls a `pulstock.cl`, `api.pulstock.cl`, y `/api/printing/print/`.

Es idempotente: si dudas, corré `pdeploy` dos veces y nada se rompe.

---

## Verificar después del deploy

```bash
pstatus
```

Salida esperada:
```
=== gunicorn ===
... 3 workers ...
=== pm2 ===
... pulstock-web online ...
=== puerto 3000 ===
LISTEN ... users:(("next-server (v1",pid=...,fd=18))
=== health ===
pulstock.cl: 200  api: 200
```

---

## Aliases útiles (configurados en `~/.bashrc` del usuario `ignacio`)

```
pdeploy        # deploy completo
pdeploy-api    # solo backend
pdeploy-web    # solo frontend
pstatus        # estado rápido (gunicorn, pm2, puerto 3000, health curls)
plogs-api      # tail logs de gunicorn
plogs-web      # tail logs del frontend (sudo pm2 logs)
plogs-nginx    # tail logs de nginx
pcd            # cd al repo (/var/www/pulstock)
pcd-api        # cd a apps/api
pcd-web        # cd a apps/web
pvenv          # source del venv del backend
pshell         # python manage.py shell con venv ya activado
pmanage <cmd>  # python manage.py <cmd> con venv ya activado
ppm2           # sudo pm2
```

---

## Rollback (si algo salió mal)

```bash
pcd
git log --oneline -5      # encontrar el commit estable previo
git checkout <hash-estable>
pdeploy                   # corre el deploy desde ese commit
```

O bien `git reset --hard HEAD~1 && pdeploy` si el problema fue el último commit.

---

## Setup inicial del servidor

Si alguna vez hay que reconstruir el servidor desde cero, los pasos están en
[`docs/ops/01-acceso-servidor.md`](docs/ops/01-acceso-servidor.md) y
[`docs/ops/02-arquitectura.md`](docs/ops/02-arquitectura.md). Resumen:

1. Ubuntu 24.04 LTS en Hetzner (CPX21 o superior).
2. Crear usuario `ignacio` con sudo.
3. Instalar Python 3.12, Node 22, PostgreSQL 16, Redis 7, Nginx, Certbot.
4. Clonar repo en `/var/www/pulstock`.
5. Backend: `pip install -r requirements.txt` en venv, configurar `.env`, `migrate`, `collectstatic`.
6. Gunicorn como systemd service (3 workers).
7. Frontend: `npm ci && npm run build` en `apps/web`, levantar con PM2 (`pulstock-web`).
8. Nginx con SSL Let's Encrypt → proxy a `localhost:8000` (api) y `localhost:3000` (web).
9. Cron de Celery beat + worker (ver `docs/ops/pulstock-crontab.txt`).

---

## Variables de entorno críticas

Todas viven en el servidor (no en Vercel ni en CI):

| Variable | Archivo | Notas |
|---|---|---|
| `DJANGO_SECRET_KEY` | `apps/api/.env` | Generar aleatoriamente |
| `DATABASE_URL` | `apps/api/.env` | `postgresql://...` |
| `WEB_ORIGIN` | `apps/api/.env` | `https://pulstock.cl,https://www.pulstock.cl` |
| `FLOW_API_KEY` / `FLOW_SECRET_KEY` | `apps/api/.env` | Credenciales Flow.cl |
| `EMAIL_HOST_PASSWORD` | `apps/api/.env` | App password de Gmail / Brevo |
| `NEXT_PUBLIC_API_URL` | `apps/web/.env.production` | `https://pulstock.cl/api` |

---

## Documentación operacional adicional

- [`docs/ops/01-acceso-servidor.md`](docs/ops/01-acceso-servidor.md) — SSH, sudo, llaves
- [`docs/ops/02-arquitectura.md`](docs/ops/02-arquitectura.md) — diagrama y servicios
- [`docs/ops/03-comandos-diarios.md`](docs/ops/03-comandos-diarios.md) — cosas que se hacen seguido
- [`docs/ops/04-deploy.md`](docs/ops/04-deploy.md) — deploy detallado + troubleshooting
- [`docs/ops/05-logs.md`](docs/ops/05-logs.md) — dónde ver qué
- [`docs/ops/06-backups.md`](docs/ops/06-backups.md) — pg_dump + retención
- [`docs/ops/07-errores-comunes.md`](docs/ops/07-errores-comunes.md) — recetas para los errores recurrentes
- [`docs/ops/08-emergencias.md`](docs/ops/08-emergencias.md) — qué hacer si se cae todo
- [`docs/ops/CHEATSHEET.md`](docs/ops/CHEATSHEET.md) — comandos copy-paste
