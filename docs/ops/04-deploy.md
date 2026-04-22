# 4. Deploy de cambios

Cómo subir código nuevo a producción.

## Flujo recomendado (1 comando)

Después de mergear un PR a `main`:

```bash
ssh ignacio@65.108.148.200
pdeploy           # deploy completo (api + web)
# o:
pdeploy-api       # solo backend (más rápido, ~10s)
pdeploy-web       # solo frontend (~1-2 min por el next build)
```

El script `~/deploy.sh` (alias `pdeploy`) hace todo en orden:

1. Asegura ownership del repo a `ignacio` (algunos archivos quedan owned by root tras deploys manuales).
2. `git pull origin main` (auto-checkout a main si estabas en otra branch).
3. Recrea el merge migration local `0018_merge_*.py` si fue eliminado por el pull (ver Notas sobre migraciones huérfanas abajo).
4. **Backend**: `migrate` + `sudo kill -HUP` al gunicorn master (workers se reciclan sin downtime).
5. **Frontend**: `next build` + `sudo pm2 stop pulstock-web` + `sudo pkill -KILL -f next-server` (importante: ver Notas sobre pm2 abajo) + `sudo pm2 start pulstock-web`.
6. Verificación final con curls a `pulstock.cl`, `api.pulstock.cl`, y al endpoint nuevo `/api/printing/print/`.

Es idempotente: corré dos veces y nada se rompe.

## Aliases útiles (configurados en `~/.bashrc`)

```
pdeploy        # deploy completo
pdeploy-api    # solo backend
pdeploy-web    # solo frontend
pstatus        # estado rápido (gunicorn, pm2, puerto 3000, health curls)
plogs-api      # tail logs de gunicorn
plogs-web      # tail logs del frontend (sudo pm2 logs)
plogs-nginx    # tail logs de nginx
pcd            # cd al repo
pcd-api        # cd a apps/api
pcd-web        # cd a apps/web
pvenv          # source del venv del backend
pshell         # python manage.py shell con venv ya activado
pmanage <cmd>  # python manage.py <cmd> con venv ya activado
ppm2           # sudo pm2
```

## Verificar después del deploy

`pdeploy` ya hace los checks al final, pero podés re-correr en cualquier momento:

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

## Rollback (si algo salió mal)

### Opción A: Volver al commit anterior

```bash
pcd
git log --oneline -5      # encontrar el commit estable previo
git checkout <hash-estable>
pdeploy                   # corre el deploy desde ese commit
```

### Opción B: Volver a HEAD~1

```bash
pcd
git reset --hard HEAD~1
pdeploy
```

## Flujo manual (si `pdeploy` falla)

Si tenés que correr cada paso a mano (debugging):

```bash
# 1. Pull
pcd && git pull origin main

# 2. Backend
pcd-api && pvenv && python manage.py migrate
sudo kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)

# 3. Frontend (¡el orden importa, ver "Notas sobre pm2")
pcd-web && npx next build
sudo pm2 stop pulstock-web
sudo pkill -KILL -f next-server      # CRÍTICO — sin esto, EADDRINUSE loop
sudo pm2 start pulstock-web

# 4. Verificar
pstatus
```

## Notas sobre pm2

**El proceso `pulstock-web` corre bajo PM2 de `root`, NO de `ignacio`.** Por eso todos los comandos pm2 de operación llevan `sudo` (alias `ppm2`).

**Bug conocido**: cuando `sudo pm2 restart pulstock-web` ejecuta el wrapper `npm start`, el child `next-server` no recibe la señal de termino y queda huérfano (adoptado por `init`). El nuevo arranque falla con `EADDRINUSE: address already in use :::3000`. **Workaround**: siempre hacer `stop` + `pkill -KILL -f next-server` + `start` en lugar de `restart`. `pdeploy` ya lo maneja.

Si ves a pm2 dando vueltas en estado `errored` con muchos restarts (`↺ 60+`), es esto. Solución:

```bash
sudo pm2 stop pulstock-web
sudo pkill -KILL -f next-server
sudo pkill -KILL -f 'next start'
sudo pm2 start pulstock-web
```

## Notas sobre migraciones huérfanas

En `apps/api/{core,forecast,purchases}/migrations/` hay archivos **que no están en git pero sí están aplicados en la DB de producción** (algunos con operations reales: `business_type`, `lead_time_days`, `holiday_extended`, etc.). Vienen de algún deploy manual antiguo donde se commitió a producción sin pushear al repo.

El más conflictivo es `apps/api/core/migrations/0018_merge_0017_cronheartbeat_0017_merge_20260405_1600.py` — fue eliminado por el PR del modelo Fudo (porque rompía `pytest` en CI), pero el merge migration que une los huérfanos con `0017_cronheartbeat` sigue siendo necesario en producción. **`pdeploy` lo recrea automáticamente como untracked después de cada pull**.

**Tarea pendiente**: limpiar este desorden en una próxima iteración. Opciones:
- Commitear los archivos huérfanos al repo (son archivos válidos con operations).
- O `migrate <app> <migration_anterior> --fake` para des-aplicar las merge migrations vacías y borrarlas del disco.

Mientras tanto, **NO eliminar** `apps/api/core/migrations/0017_merge_20260405_1600.py` ni recrear el grafo a mano — se rompe el sistema.

## Permisos del repo

Si en algún momento `git pull` falla con `insufficient permission for adding an object to repository database`, es porque algún deploy manual previo dejó archivos owned by root. Solución:

```bash
sudo chown -R ignacio:ignacio /var/www/pulstock
```

`pdeploy` hace este check automáticamente al inicio.
