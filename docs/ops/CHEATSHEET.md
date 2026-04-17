# Cheatsheet — comandos críticos de Pulstock

Imprime esto y tenlo a mano.

## Entrar al servidor
```bash
ssh root@65.108.148.200
```

## Verificar estado (4 líneas)
```bash
pm2 list
pgrep -fl "gunicorn.*api.wsgi" | head -2
curl -s http://localhost:8000/api/core/health/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
```

## Reiniciar si algo se rompe
```bash
pm2 restart pulstock-web                              # frontend
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)          # backend graceful
systemctl restart nginx                                # proxy
```

## Deploy
```bash
cd /var/www/pulstock && git pull origin main && \
cd apps/api && source venv/bin/activate && python manage.py migrate && \
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o) && \
cd ../web && npx next build && pm2 restart pulstock-web && \
echo "DEPLOY OK"
```

## Ver errores recientes
```bash
tail -50 /var/log/pulstock/gunicorn-error.log
pm2 logs pulstock-web --lines 50 --nostream
tail -50 /var/log/nginx/error.log
```

## Backup manual
```bash
sudo -u postgres pg_dump pulstock | gzip > /var/backups/pulstock/manual-$(date +%Y%m%d_%H%M).sql.gz
```

## Shell Django
```bash
cd /var/www/pulstock/apps/api
source venv/bin/activate
python manage.py shell
```

## Espacio en disco
```bash
df -h /
du -sh /var/log/*
```

## Liberar espacio rápido
```bash
logrotate -f /etc/logrotate.d/pulstock
pm2 flush
find /var/log -name "*.gz" -mtime +7 -delete
```

## Reactivar subscription de Marbrava
```python
# Shell django
from core.models import Tenant
from billing.models import Subscription
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache

t = Tenant.objects.get(slug="marbrava")
sub = Subscription.objects.get(tenant=t)
sub.status = Subscription.Status.ACTIVE
sub.current_period_end = timezone.now() + timedelta(days=365*100)
sub.trial_ends_at = None
sub.suspended_at = None
sub.payment_retry_count = 0
sub.save()
cache.delete(f"sub_access:{t.id}")
```

## Reiniciar TODO (último recurso)
```bash
systemctl restart postgresql nginx
pm2 kill && pkill -f gunicorn && sleep 2
cd /var/www/pulstock/apps/api && source venv/bin/activate && \
gunicorn api.wsgi:application --workers 3 --bind 127.0.0.1:8000 --timeout 120 --daemon \
  --access-logfile /var/log/pulstock/gunicorn-access.log \
  --error-logfile /var/log/pulstock/gunicorn-error.log
cd /var/www/pulstock/apps/web && pm2 start npm --name pulstock-web -- start && pm2 save
```

---

**Tel Hetzner:** panel https://robot.hetzner.com
**GitHub repo:** https://github.com/Iganziow/pulstock
**Flow.cl panel:** https://cuenta.flow.cl
