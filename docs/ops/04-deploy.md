# 4. Deploy de cambios

Cómo subir código nuevo a producción.

## Flow normal (cambios ya probados localmente)

### Paso 1 — En tu máquina local (push el código)

```bash
cd C:/Users/ignac/Documents/inventario-saas
git add <archivos-modificados>
git commit -m "descripción del cambio"
git push origin main
```

### Paso 2 — En el servidor (pull + rebuild)

```bash
ssh root@<TU_SERVIDOR>
```

**Si solo cambió el backend (Python):**
```bash
cd /var/www/pulstock
git pull origin main

# Si hay migraciones nuevas:
cd apps/api
source venv/bin/activate
python manage.py migrate

# Reload Gunicorn
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)
echo "Backend desplegado"
```

**Si solo cambió el frontend (Next.js):**
```bash
cd /var/www/pulstock
git pull origin main
cd apps/web
npx next build
pm2 restart pulstock-web
echo "Frontend desplegado"
```

**Si cambiaron ambos:**
```bash
cd /var/www/pulstock && \
git pull origin main && \
cd apps/api && \
source venv/bin/activate && \
python manage.py migrate && \
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o) && \
cd ../web && \
npx next build && \
pm2 restart pulstock-web && \
echo "=== DEPLOY COMPLETO ==="
```

## Verificar después del deploy

```bash
# Frontend responde
curl -s -o /dev/null -w "Frontend: %{http_code}\n" http://localhost:3000

# Backend responde
curl -s -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/api/core/health/

# Ver los últimos errores (5 min)
tail -20 /var/log/pulstock/gunicorn-error.log
pm2 logs pulstock-web --lines 20 --nostream
```

Ambos deben responder **200**.

## Rollback (si algo salió mal)

### Opción A: Volver al commit anterior

```bash
cd /var/www/pulstock

# Ver últimos commits
git log --oneline -5

# Volver al commit anterior (reemplaza HASH)
git reset --hard HASH_DEL_COMMIT_BUENO

# Rebuild
cd apps/web && npx next build && pm2 restart pulstock-web
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)
```

### Opción B: Revertir migración específica

```bash
cd /var/www/pulstock/apps/api
source venv/bin/activate

# Ver migraciones aplicadas en una app
python manage.py showmigrations billing

# Revertir a la anterior (ej. volver de 0008 a 0007)
python manage.py migrate billing 0007
```

## Cambios que NO requieren redeploy

- **Variables de entorno** (`.env`): sí requieren reiniciar Gunicorn
  ```bash
  nano /var/www/pulstock/apps/api/.env
  kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)
  ```

- **Archivos estáticos de Django** (admin CSS, etc.):
  ```bash
  cd /var/www/pulstock/apps/api
  source venv/bin/activate
  python manage.py collectstatic --noinput
  systemctl reload nginx
  ```

## Primera vez corriendo en un servidor nuevo

```bash
git clone https://github.com/Iganziow/pulstock.git /var/www/pulstock
cd /var/www/pulstock

# Backend
cd apps/api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env  # llenar variables
python manage.py migrate
python manage.py createsuperuser

# Frontend
cd ../web
npm ci
cp .env.example .env.local && nano .env.local  # llenar NEXT_PUBLIC_API_URL
npx next build

# Levantar
cd ../api
source venv/bin/activate
gunicorn api.wsgi:application --workers 3 --bind 127.0.0.1:8000 --timeout 120 --daemon \
  --access-logfile /var/log/pulstock/gunicorn-access.log \
  --error-logfile /var/log/pulstock/gunicorn-error.log

cd ../web
pm2 start npm --name pulstock-web -- start
pm2 save
pm2 startup  # autoarrancar en reboot
```
