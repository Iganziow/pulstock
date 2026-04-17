# 8. Emergencias

Guía para cuando todo está mal. Sigue los pasos en orden.

## 🚨 Escenario A: "El servidor no responde" (app caída total)

### Paso 1 — Verificar que el servidor exista

```bash
# Desde tu máquina local
ping 65.108.148.200
```

- **Responde:** el servidor está arriba, problema es con los servicios → salta al Paso 2
- **No responde:** el servidor está caído
  - Entra al panel de Hetzner: https://robot.hetzner.com
  - Verifica que la máquina esté encendida
  - Si está apagada, enciéndela desde el panel
  - Si está encendida pero no responde, reinicia forzado desde el panel

### Paso 2 — SSH al servidor

```bash
ssh root@65.108.148.200
```

- **No conecta:** red o firewall → panel Hetzner, verificar firewall
- **Conecta:** sigue abajo

### Paso 3 — Restart total de servicios

```bash
# 1. PostgreSQL
systemctl restart postgresql

# 2. Gunicorn (backend)
pkill -f gunicorn
cd /var/www/pulstock/apps/api
source venv/bin/activate
gunicorn api.wsgi:application --workers 3 --bind 127.0.0.1:8000 --timeout 120 --daemon \
  --access-logfile /var/log/pulstock/gunicorn-access.log \
  --error-logfile /var/log/pulstock/gunicorn-error.log

# 3. PM2 (frontend)
pm2 kill
cd /var/www/pulstock/apps/web
pm2 start npm --name pulstock-web -- start
pm2 save

# 4. Nginx
systemctl restart nginx

# 5. Verificar
sleep 10
curl -s http://localhost:8000/api/core/health/
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

### Paso 4 — Si aún no funciona, ver logs

```bash
tail -50 /var/log/pulstock/gunicorn-error.log
pm2 logs pulstock-web --lines 50 --nostream
tail -50 /var/log/nginx/error.log
```

---

## 🚨 Escenario B: "La data está corrupta" (reportes raros, stock negativo)

### Paso 1 — Backup de seguridad ANTES de tocar nada

```bash
BACKUP=/var/backups/pulstock/emergency-$(date +%Y%m%d_%H%M).sql.gz
sudo -u postgres pg_dump pulstock | gzip > $BACKUP
echo "Backup: $BACKUP"
ls -lh $BACKUP
```

### Paso 2 — Identificar el daño

```bash
cd /var/www/pulstock/apps/api
source venv/bin/activate
python manage.py shell
```

```python
from inventory.models import StockItem
# Stock negativo (no debería existir)
negs = StockItem.objects.filter(on_hand__lt=0)
print(f"Stock items negativos: {negs.count()}")
for s in negs[:10]:
    print(f"  {s.product.name} en {s.warehouse.name}: {s.on_hand}")

# Costo negativo
neg_costs = StockItem.objects.filter(avg_cost__lt=0)
print(f"Costos negativos: {neg_costs.count()}")
```

### Paso 3 — Corregir manualmente

```python
# Poner stock en 0 donde está negativo
from decimal import Decimal
StockItem.objects.filter(on_hand__lt=0).update(on_hand=Decimal("0"))

# Poner cost en 0 donde está negativo
StockItem.objects.filter(avg_cost__lt=0).update(avg_cost=Decimal("0"))
```

### Paso 4 — Si el daño es muy grande, restaurar desde backup

Ver `06-backups.md` → sección "RESTAURAR desde backup".

---

## 🚨 Escenario C: "Cliente dice que le cobré mal" (dispute de venta)

### Paso 1 — Buscar la venta

```python
from sales.models import Sale, SaleLine
from core.models import Tenant

t = Tenant.objects.get(slug="SLUG_CLIENTE")
# Buscar por fecha
sales = Sale.objects.filter(tenant=t, created_at__date="2026-04-16").order_by("-id")
for s in sales[:20]:
    print(f"#{s.sale_number} | ${s.total} | {s.status} | {s.created_by.username}")

# Ver detalle
s = Sale.objects.get(id=SALE_ID)
for l in s.lines.all():
    print(f"  {l.product.name} x{l.qty} = ${l.line_total}")
for p in s.payments.all():
    print(f"  Pago {p.method}: ${p.amount}")
```

### Paso 2 — Anular venta si corresponde

```python
s.status = "VOID"
s.void_reason = "Reclamo cliente: [razón]"
s.save()

# Devolver stock
from inventory.models import StockItem
for l in s.lines.all():
    si = StockItem.objects.get(warehouse=s.warehouse, product=l.product)
    si.on_hand += l.qty
    si.save()
```

### Paso 3 — Documentar

Siempre guarda el cambio: fecha, razón, monto, quién pidió.

---

## 🚨 Escenario D: "Mario perdió acceso / nadie puede entrar"

### Paso 1 — Verificar subscription de Marbrava

```python
from core.models import Tenant
from billing.models import Subscription

t = Tenant.objects.get(slug="marbrava")
sub = Subscription.objects.get(tenant=t)
print(f"Status: {sub.status}")
print(f"Allowed: {sub.is_access_allowed}")
print(f"Lifetime? {t.slug in ['marbrava']}")  # debe ser True
```

### Paso 2 — Si no está en lifetime_slugs, forzar

```bash
# Verificar env
grep LIFETIME /var/www/pulstock/apps/api/.env
# Debe tener: BILLING_LIFETIME_SLUGS=marbrava

# Si no, agregar:
echo "BILLING_LIFETIME_SLUGS=marbrava" >> /var/www/pulstock/apps/api/.env

# Reload Gunicorn
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)
```

### Paso 3 — Forzar sub activa

```python
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache

sub.status = Subscription.Status.ACTIVE
sub.current_period_end = timezone.now() + timedelta(days=365*100)
sub.trial_ends_at = None
sub.payment_retry_count = 0
sub.suspended_at = None
sub.save()
cache.delete(f"sub_access:{t.id}")
print("Marbrava reactivada")
```

---

## 🚨 Escenario E: Disco al 100%

```bash
df -h /
# Si está al 100%, NADIE puede escribir (app se congela)

# Limpieza inmediata
logrotate -f /etc/logrotate.d/pulstock 2>/dev/null
journalctl --vacuum-time=2d
pm2 flush
truncate -s 0 /var/log/pulstock/*.log
find /var/log -name "*.gz" -mtime +7 -delete 2>/dev/null
find /tmp -type f -mtime +3 -delete 2>/dev/null

# Si el problema persiste, ver qué ocupa más
du -sh /var/* 2>/dev/null | sort -hr | head -10
du -sh /home/* 2>/dev/null | sort -hr | head -10
```

---

## 🚨 Escenario F: Todo funciona pero Flow no procesa pagos

### Diagnóstico

```bash
# Ver webhooks recibidos de Flow
grep "webhook/flow" /var/log/nginx/access.log | tail -20

# Ver errores relacionados con Flow
grep -i "flow" /var/log/pulstock/gunicorn-error.log | tail -30

# Verificar variables de entorno
grep FLOW /var/www/pulstock/apps/api/.env
```

### Verificar estado con Flow

```python
from billing.models import Subscription, Invoice
# Últimas facturas pendientes
for i in Invoice.objects.filter(status="pending").order_by("-id")[:10]:
    print(f"#{i.id} | ${i.amount_clp} | {i.created_at} | order={i.gateway_order_id}")
```

Si una factura está pendiente pero el cliente dice que pagó:
1. Verifica en el panel de Flow (https://cuenta.flow.cl) que la orden existe
2. Si pagó, marca manual:
   ```python
   from django.utils import timezone
   i = Invoice.objects.get(id=FACTURA_ID)
   i.status = "paid"
   i.paid_at = timezone.now()
   i.save()
   
   from billing.services import activate_period
   activate_period(i.subscription, i)
   ```

---

## 🚨 Escenario G: Ataque DDoS o tráfico anormal

```bash
# Ver conexiones activas
netstat -an | grep ESTABLISHED | wc -l

# IPs que más requests hacen (últimas 1000)
tail -1000 /var/log/nginx/access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head -10

# Bloquear IP específica
ufw deny from IP.MAL.ICIOSA
# o con iptables
iptables -A INPUT -s IP.MAL.ICIOSA -j DROP
```

---

## Checklist para contactar soporte externo

Si llegaste acá y nada funciona, antes de llamar:

- [ ] Logs del backend (últimas 100 líneas)
- [ ] Logs del frontend (últimas 100 líneas)
- [ ] Logs de Nginx
- [ ] Output de `pm2 list` y `systemctl status nginx postgresql`
- [ ] Fecha y hora exacta del problema
- [ ] Qué estabas haciendo cuando se rompió
- [ ] Qué has intentado ya

Guarda todo en un archivo:

```bash
mkdir -p /tmp/debug-$(date +%Y%m%d_%H%M)
cd /tmp/debug-*
cp /var/log/pulstock/*.log .
cp /var/log/nginx/error.log .
pm2 list > pm2.txt
pm2 logs --nostream --lines 200 > pm2-logs.txt
systemctl status nginx postgresql > services.txt
df -h > disk.txt
free -h > memory.txt
tar -czf /tmp/debug.tar.gz /tmp/debug-*/
echo "Debug package: /tmp/debug.tar.gz"
```

Descarga ese `.tar.gz` con `scp` y envíalo.
