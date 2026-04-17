# 9. Mantenimiento periódico

Tareas que tienes que hacer **aunque todo funcione bien**.

## 📅 Semanal (5 minutos)

```bash
ssh root@65.108.148.200

# 1. Estado general
pm2 list
pgrep -fl "gunicorn.*api.wsgi" | head -2
df -h /
free -h

# 2. Verificar backups recientes
ls -lt /var/backups/pulstock/ | head -5
# Debe haber un backup de hoy o ayer

# 3. Errores recientes en el backend
tail -50 /var/log/pulstock/gunicorn-error.log

# 4. Últimos tracebacks (si hay)
grep -c Traceback /var/log/pulstock/gunicorn-error.log
```

**Qué te debería preocupar:**
- Disco >80% usado
- Más de 5 tracebacks en la semana
- PM2 mostrando restart frecuentes (columna `↺` subiendo rápido)

---

## 📅 Mensual (20 minutos)

### 1. Copia de backup fuera del servidor

```bash
# Desde tu máquina local
scp root@65.108.148.200:/var/backups/pulstock/pulstock_$(date +%Y%m%d)_0300.sql.gz ~/Desktop/pulstock_backup_$(date +%Y%m).sql.gz
```

Guarda en Google Drive / Dropbox / disco externo.

### 2. Actualización de paquetes del sistema (con cuidado)

```bash
ssh root@65.108.148.200

# Ver qué se actualizaría
apt list --upgradable 2>/dev/null | head -20

# Actualizar solo parches de seguridad
apt update
apt upgrade -y --only-upgrade $(apt list --upgradable 2>/dev/null | grep -i security | awk -F/ '{print $1}')

# NO hacer full upgrade en producción sin probar antes
```

### 3. Revisar crecimiento de la base de datos

```bash
sudo -u postgres psql pulstock <<SQL
SELECT pg_size_pretty(pg_database_size('pulstock'));
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname='public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
SQL
```

Si alguna tabla crece rápido anormalmente, investigar.

### 4. Limpiar logs antiguos

```bash
# Logs rotados >30 días
find /var/log -name "*.gz" -mtime +30 -delete

# Backups >30 días (si ya copiaste fuera)
find /var/backups/pulstock -name "*.sql.gz" -mtime +30 -delete

# PM2 logs
pm2 flush
```

### 5. Verificar que cron jobs corren

```bash
# Logs del cron de expire_trials
ls -la /var/log/pulstock/expire_trials.log
tail -20 /var/log/pulstock/expire_trials.log

# Logs de backups
tail -20 /var/backups/pulstock/backup.log
```

---

## 📅 Trimestral (1 hora)

### 1. Probar restauración de backup

⚠️ **Hazlo en un servidor de prueba, NO en producción.**

```bash
# En una VPS de prueba o en Docker
# 1. Copia el último backup
scp root@65.108.148.200:/var/backups/pulstock/pulstock_$(date +%Y%m%d)_0300.sql.gz /tmp/

# 2. Crea BD temporal y restaura
sudo -u postgres psql -c "CREATE DATABASE pulstock_test;"
zcat /tmp/pulstock_*.sql.gz | sudo -u postgres psql pulstock_test

# 3. Verifica
sudo -u postgres psql pulstock_test -c "SELECT COUNT(*) FROM core_user;"
sudo -u postgres psql pulstock_test -c "SELECT COUNT(*) FROM sales_sale;"

# 4. Limpia
sudo -u postgres psql -c "DROP DATABASE pulstock_test;"
```

Si no se restaura limpio, tu backup está corrupto → **alerta crítica**.

### 2. Revisar certificado SSL (si configuraste dominio)

```bash
# Ver cuándo vence
certbot certificates

# Simular renovación (no la ejecuta)
certbot renew --dry-run
```

Si el dry-run falla, corregir antes de que el certificado expire de verdad.

### 3. Auditar usuarios

```python
# En Django shell
from core.models import User
from datetime import timedelta
from django.utils import timezone

# Usuarios que nunca iniciaron sesión (puede ser que se olvidaron)
ghost_users = User.objects.filter(last_login__isnull=True, is_active=True)
for u in ghost_users:
    print(f"  {u.username} (creado {u.date_joined})")

# Usuarios que no entran hace >90 días (considerar desactivar)
old = User.objects.filter(
    last_login__lt=timezone.now() - timedelta(days=90),
    is_active=True,
)
for u in old:
    print(f"  {u.username} último login: {u.last_login}")
```

### 4. Revisar dependencias con vulnerabilidades

```bash
# Backend
cd /var/www/pulstock/apps/api
source venv/bin/activate
pip list --outdated

# Frontend
cd /var/www/pulstock/apps/web
npm audit
```

No actualices todo de golpe. Solo parches de seguridad críticos, probando antes.

---

## 📅 Anual

### 1. Rotar secrets

- `DJANGO_SECRET_KEY` (con cuidado: invalida sesiones activas)
- Credenciales de Flow.cl (si cambiaron)
- Password del servidor (siempre)

### 2. Revisar configuración de seguridad

```bash
# Firewall
ufw status verbose

# Fail2ban (si está instalado)
fail2ban-client status

# SSH solo por llave pública
grep "PasswordAuthentication" /etc/ssh/sshd_config
# Debe ser: PasswordAuthentication no (si ya tienes llaves configuradas)
```

### 3. Actualización mayor de OS

Ubuntu/Debian releases cada 2 años. Si el OS está próximo al EOL, planificar migración a un servidor nuevo con OS reciente.

---

## 📋 Checklist de salud mensual

Copia esto en un documento y marca cada mes:

```
[ ] Backup reciente existe y tiene tamaño normal
[ ] Backup copiado fuera del servidor
[ ] Disco <80%
[ ] RAM disponible
[ ] PM2 y Gunicorn corriendo sin restarts anormales
[ ] Sin tracebacks nuevos en logs
[ ] Subscription de Marbrava activa
[ ] Cron de expire_trials ejecutándose
[ ] Certificado SSL no expira en <30 días
[ ] Tests pasan (en local, antes de próximo deploy)
```

---

## 📞 Cuándo pedir ayuda

- **Disco al 95%+ y no puedo liberarlo** → hay que agregar espacio o migrar servidor
- **Base de datos corrupta** → restaurar desde backup
- **Certificado SSL expira mañana** → renovación urgente
- **Flow.cl cambió su API** → actualizar código (ver changelog de Flow)
- **Vulnerabilidad crítica en Django/Next.js** → actualizar versión mayor
