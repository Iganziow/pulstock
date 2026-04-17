# 5. Revisar logs

Dónde buscar cuando algo falla.

## Ubicación de logs

| Qué | Archivo |
|-----|---------|
| Backend errores | `/var/log/pulstock/gunicorn-error.log` |
| Backend requests | `/var/log/pulstock/gunicorn-access.log` |
| Frontend (PM2) | `~/.pm2/logs/pulstock-web-out.log` y `-error.log` |
| Nginx errores | `/var/log/nginx/error.log` |
| Nginx requests | `/var/log/nginx/access.log` |
| Expire trials | `/var/log/pulstock/expire_trials.log` |
| Backups | `/var/backups/pulstock/backup.log` |
| PostgreSQL | `/var/log/postgresql/postgresql-*.log` |

## Ver logs en tiempo real

```bash
# Backend en vivo
tail -f /var/log/pulstock/gunicorn-error.log

# Frontend en vivo (con streaming)
pm2 logs pulstock-web

# Varios a la vez
tail -f /var/log/pulstock/gunicorn-error.log /var/log/nginx/error.log
```

## Buscar errores específicos

```bash
# Errores 500 en las últimas 100 líneas
grep "500" /var/log/nginx/access.log | tail -20

# Tracebacks de Python del último día
grep -A 20 "Traceback" /var/log/pulstock/gunicorn-error.log | tail -50

# Errores de Flow (webhook)
grep -i "flow" /var/log/pulstock/gunicorn-error.log | tail -30

# Ver requests a un endpoint específico
grep "/api/sales/" /var/log/pulstock/gunicorn-access.log | tail -20

# Ver solo requests con status 4xx o 5xx
awk '$9 ~ /^[45]/ {print}' /var/log/pulstock/gunicorn-access.log | tail -20
```

## Analizar un error específico

Si un cliente reporta un error a las 14:30:

```bash
# Backend — error en esa hora
grep "14:30" /var/log/pulstock/gunicorn-error.log

# Nginx — requests en esa hora
awk '/14:30/' /var/log/nginx/access.log | head -50

# Frontend — logs en esa hora (ajusta fecha)
pm2 logs pulstock-web --lines 500 --nostream | grep -i "14:30"
```

## Tamaño y rotación de logs

```bash
# Tamaño actual
ls -lh /var/log/pulstock/
ls -lh /var/log/nginx/

# Ver si logrotate está activo
cat /etc/logrotate.d/pulstock
# (debe existir: rotación semanal, 4 semanas, comprimido)

# Forzar rotación manual (si los logs están enormes)
logrotate -f /etc/logrotate.d/pulstock
```

## Limpiar logs si el disco se llena (emergencia)

```bash
# Truncar log grande (sin borrarlo, para no romper el proceso que escribe)
truncate -s 0 /var/log/pulstock/gunicorn-access.log

# Borrar logs viejos (>30 días)
find /var/log/pulstock/ -name "*.gz" -mtime +30 -delete
find /var/log/nginx/ -name "*.gz" -mtime +30 -delete

# Limpiar logs de PM2
pm2 flush
```

## Interpretar logs comunes

### Gunicorn normal

```
[2026-04-16 10:30:45 +0000] [12345] [INFO] Starting gunicorn 21.2.0
[2026-04-16 10:30:45 +0000] [12345] [INFO] Listening at: http://127.0.0.1:8000
```

### Gunicorn worker timeout (pedido muy lento)

```
[CRITICAL] WORKER TIMEOUT (pid:12345)
```
**Causa:** una query DB muy lenta o endpoint que tarda >120s.
**Fix:** investigar la query, optimizar.

### Traceback típico

```
Traceback (most recent call last):
  File "/var/www/pulstock/apps/api/billing/views.py", line 556, in post
    ...
AttributeError: 'NoneType' object has no attribute 'X'
```
**Fix:** ve a la línea, identifica variable que es None.

### Nginx "upstream not found"

```
connect() failed (111: Connection refused) while connecting to upstream
```
**Causa:** Gunicorn o PM2 caídos.
**Fix:** `pm2 restart pulstock-web` o reiniciar Gunicorn.
