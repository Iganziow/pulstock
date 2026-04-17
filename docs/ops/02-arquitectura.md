# 2. Arquitectura de producción

## Qué corre y dónde

```
Internet
   ↓ (HTTP puerto 80)
NGINX (reverse proxy)
   ├─→ / → PM2 (pulstock-web) → Next.js puerto 3000
   ├─→ /api/* → Gunicorn (3 workers) → Django puerto 8000
   └─→ /static, /media → disco directo
                    ↓
              PostgreSQL puerto 5432 (local)
```

## Verificar que todo corre

```bash
# 1. Frontend (PM2)
pm2 list
# Debe mostrar: pulstock-web | online

# 2. Backend (Gunicorn)
ps aux | grep gunicorn | grep -v grep
# Debe mostrar 4 procesos (1 master + 3 workers)

# 3. Nginx
systemctl status nginx
# Debe decir: active (running)

# 4. PostgreSQL
systemctl status postgresql
# Debe decir: active (running)
```

## Un-liner para verificar salud completa

```bash
echo "=== FRONTEND ===" && pm2 list && \
echo "=== BACKEND ===" && pgrep -fl "gunicorn.*api.wsgi" | head -5 && \
echo "=== NGINX ===" && systemctl is-active nginx && \
echo "=== POSTGRES ===" && systemctl is-active postgresql && \
echo "=== API HEALTH ===" && curl -s http://localhost:8000/api/core/health/ && \
echo "" && echo "=== WEB HEALTH ===" && curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 && echo ""
```

Si todo está bien ves:
```
FRONTEND: pulstock-web online
BACKEND: 4 procesos gunicorn
NGINX: active
POSTGRES: active
API: {"status":"ok"}
WEB: 200
```
