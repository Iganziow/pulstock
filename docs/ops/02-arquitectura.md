# 2. Arquitectura de producción

## Qué corre y dónde

```
Internet
   ↓ (HTTPS puerto 443 — pulstock.cl / api.pulstock.cl)
NGINX (reverse proxy, certificado de certbot que se renueva solo)
   ├─→ / → PM2 (pulstock-web) → Next.js puerto 3000
   ├─→ /api/* → Gunicorn (5 workers) → Django puerto 8000
   └─→ /static, /media → disco directo
                    ↓
              PostgreSQL puerto 5432 (local)
```

## Verificar que todo corre

```bash
# 1. Frontend (PM2)
sudo pm2 list
# Debe mostrar: pulstock-web | online
#
# El `sudo` NO es opcional: PM2 corre como root. Sin el, la tabla sale vacia
# y parece que el frontend esta caido cuando en realidad esta perfecto.

# 2. Backend (Gunicorn)
ps -eo args | grep -c "[g]unicorn.*api.wsgi"
# Debe dar 6: 1 master + 5 workers (--workers 5)
#
# Los corchetes en [g]unicorn no son un error de tipeo: evitan que el propio
# grep se cuente a si mismo y devuelva uno de mas.

# 3. Nginx
systemctl status nginx
# Debe decir: active (running)

# 4. PostgreSQL
systemctl status postgresql
# Debe decir: active (running)
```

## Un-liner para verificar salud completa

```bash
echo "=== FRONTEND ===" && sudo pm2 list && \
echo "=== BACKEND ===" && ps -eo args | grep -c "[g]unicorn.*api.wsgi" && \
echo "=== NGINX ===" && systemctl is-active nginx && \
echo "=== POSTGRES ===" && systemctl is-active postgresql && \
echo "=== API HEALTH ===" && curl -s http://localhost:8000/api/core/health/ && \
echo "" && echo "=== WEB HEALTH ===" && curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 && echo ""
```

Si todo está bien ves:
```
FRONTEND: pulstock-web online
BACKEND: 6 procesos gunicorn
NGINX: active
POSTGRES: active
API: {"status":"ok"}
WEB: 200
```

## Chequeo profundo

`/api/core/health/` solo dice que Django responde. Para saber si la base, el
disco y las tareas programadas están sanos:

```bash
curl -s https://api.pulstock.cl/api/core/health/deep/
```

Devuelve `200` si está sano y `503` si algo se degradó — sirve directo como
monitor externo, sin token.
