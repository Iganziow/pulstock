# 7. Errores comunes y cómo arreglarlos

Los problemas que más vas a ver en producción, con su solución.

---

## 🔴 La app no carga (timeout / error de conexión)

### Diagnóstico rápido

```bash
ssh root@<TU_SERVIDOR>
pm2 list
pgrep -fl "gunicorn.*api.wsgi"
systemctl is-active nginx
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/core/health/
```

### Caso A: PM2 dice `stopped` o `errored`

```bash
pm2 logs pulstock-web --lines 30 --nostream
pm2 restart pulstock-web

# Si no levanta:
fuser -k 3000/tcp
pm2 delete pulstock-web
cd /var/www/pulstock/apps/web
pm2 start npm --name pulstock-web -- start
pm2 save
```

### Caso B: Gunicorn no responde

```bash
# Reload graceful
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)

# Si no funciona, hard restart
pkill -f gunicorn
cd /var/www/pulstock/apps/api
source venv/bin/activate
gunicorn api.wsgi:application --workers 3 --bind 127.0.0.1:8000 --timeout 120 --daemon \
  --access-logfile /var/log/pulstock/gunicorn-access.log \
  --error-logfile /var/log/pulstock/gunicorn-error.log \
  --chdir /var/www/pulstock/apps/api
```

### Caso C: Nginx caído

```bash
systemctl start nginx
# Si falla al arrancar, ver error:
nginx -t
journalctl -u nginx -n 20
```

---

## 🔴 Error 502 Bad Gateway

Nginx está arriba pero no puede conectar al backend.

```bash
# Verificar Gunicorn
pgrep -fl "gunicorn.*api.wsgi"
# Si no hay procesos → iniciar Gunicorn (ver Caso B arriba)

# Verificar PM2
pm2 list
# Si pulstock-web no está online → pm2 restart pulstock-web
```

---

## 🔴 Error 504 Gateway Timeout

Backend tardó más de 120s en responder.

```bash
# Ver qué endpoint está lento
tail -100 /var/log/pulstock/gunicorn-access.log | awk '$NF > 10 {print}'

# Ver query lentas en PostgreSQL
sudo -u postgres psql pulstock -c "SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '30 seconds';"

# Matar query específica si hay que hacerlo
sudo -u postgres psql pulstock -c "SELECT pg_cancel_backend(PID);"
```

---

## 🔴 "Disk full" — disco lleno

```bash
# Ver qué ocupa espacio
df -h /
du -sh /var/log/* 2>/dev/null | sort -hr | head
du -sh /var/www/pulstock/* 2>/dev/null | sort -hr | head

# Limpiar logs
logrotate -f /etc/logrotate.d/pulstock
find /var/log/pulstock -name "*.gz" -mtime +7 -delete
find /var/log/nginx -name "*.gz" -mtime +7 -delete
pm2 flush

# Limpiar builds viejos de Next.js
du -sh /var/www/pulstock/apps/web/.next*

# Limpiar backups viejos (si tienes copia externa)
find /var/backups/pulstock -name "*.sql.gz" -mtime +14 -delete
```

---

## 🔴 "FATAL: too many connections" — PostgreSQL sin conexiones

```bash
# Ver conexiones activas
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Ver quién las está consumiendo
sudo -u postgres psql -c "SELECT datname, usename, count(*) FROM pg_stat_activity GROUP BY datname, usename;"

# Matar conexiones idle de la app
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='pulstock' AND state='idle' AND state_change < now() - interval '10 minutes';"

# Si persiste, reiniciar PostgreSQL (cuidado: corta todas las conexiones)
systemctl restart postgresql
# Y después reiniciar el backend
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)
```

---

## 🔴 "Worker timeout" en logs de Gunicorn

Algún endpoint tarda demasiado.

```bash
# Ver cuál endpoint
grep -B 3 "WORKER TIMEOUT" /var/log/pulstock/gunicorn-error.log | tail -20

# Ver últimas requests antes del timeout
tail -100 /var/log/pulstock/gunicorn-access.log
```

Solución: optimizar el endpoint o aumentar timeout en el comando de Gunicorn.

---

## 🔴 Mario dice "no puedo iniciar sesión"

### Diagnóstico

```bash
cd /var/www/pulstock/apps/api
source venv/bin/activate
python manage.py shell
```

```python
from core.models import User
u = User.objects.get(username="mario")   # o su email
print(u.is_active, u.tenant.name if u.tenant else None)
print(u.check_password("PASSWORD_QUE_INTENTA"))  # True/False
```

### Causas comunes

**"is_active=False"** → reactivar:
```python
u.is_active = True
u.save()
```

**Password olvidado** → resetear:
```python
u.set_password("NUEVA_PASSWORD")
u.save()
```

**Subscription suspended** → verificar y reactivar si corresponde:
```python
from billing.models import Subscription
sub = Subscription.objects.get(tenant=u.tenant)
print(sub.status, sub.is_access_allowed)
```

---

## 🔴 "Tu suscripción está suspendida" (402)

### Diagnóstico

```bash
cd /var/www/pulstock/apps/api
source venv/bin/activate
python manage.py shell
```

```python
from core.models import Tenant
from billing.models import Subscription

t = Tenant.objects.get(slug="SLUG_DEL_CLIENTE")
sub = Subscription.objects.get(tenant=t)
print(f"Status: {sub.status}")
print(f"Plan: {sub.plan.key} ${sub.plan.price_clp}")
print(f"Trial ends: {sub.trial_ends_at}")
print(f"Period end: {sub.current_period_end}")
print(f"Suspended at: {sub.suspended_at}")
print(f"Retry count: {sub.payment_retry_count}")
```

### Reactivar manualmente (si el cliente pagó fuera del sistema)

```python
from django.utils import timezone
from datetime import timedelta

sub.status = Subscription.Status.ACTIVE
sub.current_period_start = timezone.now()
sub.current_period_end = timezone.now() + timedelta(days=30)
sub.payment_retry_count = 0
sub.next_retry_at = None
sub.suspended_at = None
sub.save()

# Invalidar cache
from django.core.cache import cache
cache.delete(f"sub_access:{t.id}")
print("Subscription reactivada")
```

---

## 🔴 Impresora Bluetooth no imprime

**Causa común:** La impresora perdió conexión o batería.

Pídele al cliente:
1. Apagar y prender la impresora
2. En el dashboard, ir a `Configuración → Impresoras`
3. Eliminar la impresora y agregarla de nuevo (Bluetooth)

Si persiste: revisar que Chrome esté actualizado (WebBluetooth API).

---

## 🔴 Venta duplicada (mismo producto 2 veces)

### Diagnóstico

```python
from sales.models import Sale
# Buscar ventas del día con misma idempotency_key
Sale.objects.filter(created_at__date="2026-04-16").order_by("idempotency_key").values("id", "idempotency_key", "total")
```

Si hay 2 sales con misma `idempotency_key`, el sistema falló en la idempotencia (no debería pasar). Anular la duplicada:

```python
from sales.models import Sale
dup = Sale.objects.get(id=ID_DUPLICADO)
dup.status = "VOID"
dup.save()
# Reversar stock manualmente si ya se había descontado
```

---

## 🔴 Frontend muestra "Error de conexión"

1. Verificar que el backend responde:
   ```bash
   curl http://localhost:8000/api/core/health/
   ```

2. Verificar que Nginx pasa `/api/*` al backend:
   ```bash
   nginx -t
   cat /etc/nginx/sites-enabled/pulstock | grep -A 5 "location /api"
   ```

3. Verificar CORS en settings (si el dominio cambió):
   ```bash
   grep WEB_ORIGIN /var/www/pulstock/apps/api/.env
   ```

---

## 🔴 "ALLOWED_HOSTS" error (Invalid HTTP_HOST)

Pasa cuando se agrega un dominio nuevo.

```bash
# Editar .env
nano /var/www/pulstock/apps/api/.env
# Agregar el nuevo dominio a DJANGO_ALLOWED_HOSTS=...

# Reload Gunicorn
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)
```

---

## 🔴 SSL expirado (HTTPS no funciona)

Si usas Let's Encrypt:

```bash
# Renovar manual
certbot renew

# Verificar estado
certbot certificates

# Si no renueva automático, verificar cron
cat /etc/cron.d/certbot
```

---

## 🔴 PM2 no arranca automáticamente al reiniciar servidor

```bash
# Guardar los procesos actuales
pm2 save

# Configurar autoarranque
pm2 startup
# (copia y ejecuta el comando que te devuelve)

# Verificar
systemctl status pm2-root
```

---

## 🚨 Cuando nada funciona — reinicio completo

```bash
ssh root@<TU_SERVIDOR>

# 1. Reiniciar todo
systemctl restart postgresql
systemctl restart nginx
pm2 kill

# 2. Matar gunicorn si queda colgado
pkill -f gunicorn

# 3. Levantar Gunicorn
cd /var/www/pulstock/apps/api
source venv/bin/activate
gunicorn api.wsgi:application --workers 3 --bind 127.0.0.1:8000 --timeout 120 --daemon \
  --access-logfile /var/log/pulstock/gunicorn-access.log \
  --error-logfile /var/log/pulstock/gunicorn-error.log

# 4. Levantar PM2
cd /var/www/pulstock/apps/web
pm2 start npm --name pulstock-web -- start
pm2 save

# 5. Verificar todo
sleep 5
curl http://localhost:8000/api/core/health/
curl -o /dev/null -s -w "%{http_code}" http://localhost:3000
```
