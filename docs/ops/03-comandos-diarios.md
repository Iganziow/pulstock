# 3. Comandos diarios

Los comandos que más vas a usar, listos para copiar y pegar.

## Verificar estado general (5 segundos)

```bash
ssh root@65.108.148.200
pm2 list && pgrep -fl "gunicorn.*api.wsgi" | head -1 && df -h / | tail -1
```

## Reiniciar frontend (Next.js)

```bash
pm2 restart pulstock-web
```

Si el puerto 3000 está ocupado:
```bash
fuser -k 3000/tcp
pm2 delete pulstock-web
cd /var/www/pulstock/apps/web
pm2 start npm --name pulstock-web -- start
pm2 save
```

## Reiniciar backend (Django/Gunicorn)

**Graceful** (sin cortar conexiones activas):
```bash
kill -HUP $(pgrep -f 'gunicorn.*api.wsgi' -o)
```

**Hard restart** (si el graceful no responde):
```bash
pkill -f gunicorn
cd /var/www/pulstock/apps/api
source venv/bin/activate
gunicorn api.wsgi:application \
  --workers 3 --bind 127.0.0.1:8000 --timeout 120 --daemon \
  --access-logfile /var/log/pulstock/gunicorn-access.log \
  --error-logfile /var/log/pulstock/gunicorn-error.log \
  --chdir /var/www/pulstock/apps/api
```

## Reiniciar Nginx

```bash
# Solo reload (sin cortar conexiones)
systemctl reload nginx

# Full restart
systemctl restart nginx

# Verificar config antes de reload
nginx -t
```

## Ver logs en vivo

```bash
# Backend (errores)
tail -f /var/log/pulstock/gunicorn-error.log

# Backend (requests)
tail -f /var/log/pulstock/gunicorn-access.log

# Frontend
pm2 logs pulstock-web --lines 50

# Nginx
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

## Entrar a la consola de Django (shell)

```bash
cd /var/www/pulstock/apps/api
source venv/bin/activate
python manage.py shell
```

Dentro del shell puedes consultar/modificar datos:
```python
from core.models import Tenant, User
from billing.models import Subscription

# Ver todos los tenants
for t in Tenant.objects.all():
    print(t.name, t.slug, t.is_active)

# Ver subscription de Marbrava
sub = Subscription.objects.get(tenant__slug="marbrava")
print(sub.status, sub.is_access_allowed)

# Salir: Ctrl+D o exit()
```

## Estado de PostgreSQL

```bash
# Conectarse a la base de datos
sudo -u postgres psql pulstock

# Dentro de psql:
\dt                   # listar tablas
\d core_user          # ver estructura de una tabla
SELECT COUNT(*) FROM core_user;
\q                    # salir
```

## Espacio en disco

```bash
df -h /                    # raíz
du -sh /var/log/*          # qué ocupa cada carpeta de logs
du -sh /var/www/pulstock   # app completa
du -sh /var/backups/*      # backups
```

## Ver procesos que consumen RAM/CPU

```bash
# Top 10 por RAM
ps aux --sort=-%mem | head -10

# Top 10 por CPU
ps aux --sort=-%cpu | head -10

# Interactivo
htop    # si no está: apt install htop
```
