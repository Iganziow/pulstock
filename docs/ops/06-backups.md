# 6. Backups

Respaldos automáticos y cómo restaurar.

## Backups automáticos (ya configurados)

Todos los días a las **3:00 AM** corre un dump de PostgreSQL:

```bash
# Verificar configuración
crontab -l  # debe mostrar línea con pulstock/backup.sh o similar
ls -la /var/backups/pulstock/
```

**Ubicación:** `/var/backups/pulstock/pulstock_YYYYMMDD_0300.sql.gz`

Se conservan **8 días** de historial (se rotan automáticamente).

## Hacer backup manual ahora

```bash
# Backup completo
sudo -u postgres pg_dump pulstock | gzip > /var/backups/pulstock/pulstock_manual_$(date +%Y%m%d_%H%M).sql.gz

# Verificar que se creó y no está vacío
ls -lh /var/backups/pulstock/pulstock_manual_*.sql.gz
```

## Backup rápido antes de cambio peligroso

Antes de hacer una migración o cambio grande, siempre:

```bash
BACKUP_FILE=/var/backups/pulstock/pre-change-$(date +%Y%m%d_%H%M).sql.gz
sudo -u postgres pg_dump pulstock | gzip > $BACKUP_FILE
echo "Backup creado: $BACKUP_FILE"
ls -lh $BACKUP_FILE
```

## Validar que un backup es válido

```bash
# Ver las primeras y últimas líneas
zcat /var/backups/pulstock/pulstock_20260416_0300.sql.gz | head -5
zcat /var/backups/pulstock/pulstock_20260416_0300.sql.gz | tail -5

# Debe empezar con: "-- PostgreSQL database dump"
# Debe terminar con: "-- PostgreSQL database dump complete"
```

## RESTAURAR desde backup (⚠️ peligroso)

**Esto BORRA toda la data actual y la reemplaza.** Solo úsalo en desastre real.

### Paso 1: Detener todo lo que escribe a la BD

```bash
# Detener backend
kill -9 $(pgrep -f 'gunicorn.*api.wsgi')
sudo pm2 stop pulstock-web

# Verificar que no haya conexiones
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='pulstock';"
```

### Paso 2: Borrar y recrear la BD

```bash
sudo -u postgres psql <<SQL
DROP DATABASE pulstock;
CREATE DATABASE pulstock OWNER pulstock_user;
SQL
```

### Paso 3: Restaurar el dump

```bash
# Reemplaza la fecha del backup que quieres restaurar
BACKUP=/var/backups/pulstock/pulstock_20260416_0300.sql.gz

zcat $BACKUP | sudo -u postgres psql pulstock
echo "Restauración completada. Verifica con una query:"
sudo -u postgres psql pulstock -c "SELECT COUNT(*) FROM core_tenant;"
```

### Paso 4: Reiniciar servicios

```bash
sudo systemctl restart pulstock-api

sudo pm2 start pulstock-web
```

## Backup fuera del servidor (recomendado mensual)

Para evitar pérdida total si el servidor muere:

```bash
# Descarga el backup más reciente a tu máquina local
scp ignacio@65.108.148.200:/var/backups/pulstock/pulstock_$(date +%Y%m%d)_0300.sql.gz ~/Desktop/
```

Guárdalo en Google Drive / Dropbox / disco externo.

## Backup del código

El código vive en GitHub (https://github.com/Iganziow/pulstock). Si el servidor muere, clonas de nuevo.

```bash
# En servidor nuevo
git clone https://github.com/Iganziow/pulstock.git /var/www/pulstock
```

## Checklist: ¿estoy protegido contra pérdida de datos?

- ✅ Backup diario automático a las 3 AM
- ✅ 8 días de historial
- ✅ Código en GitHub
- ⚠️ Hacer backup mensual fuera del servidor (copia manual)
- ⚠️ Probar restauración 1 vez al año para verificar que funciona

## Script de restore (para emergencias)

Guarda este script en `/root/restore.sh` para restaurar rápido:

```bash
cat > /root/restore.sh << 'RESTORE_EOF'
#!/bin/bash
# Uso: bash /root/restore.sh /var/backups/pulstock/pulstock_YYYYMMDD_0300.sql.gz
set -e
BACKUP=$1
if [ -z "$BACKUP" ] || [ ! -f "$BACKUP" ]; then
  echo "Uso: $0 <archivo_backup.sql.gz>"
  exit 1
fi
echo "⚠️  Este comando BORRA la BD actual y restaura desde $BACKUP"
read -p "¿Continuar? (yes/no): " confirm
[ "$confirm" = "yes" ] || exit 1

kill -9 $(pgrep -f 'gunicorn.*api.wsgi') 2>/dev/null || true
sudo pm2 stop pulstock-web

sudo -u postgres psql -c "DROP DATABASE IF EXISTS pulstock;"
sudo -u postgres psql -c "CREATE DATABASE pulstock OWNER pulstock_user;"
zcat $BACKUP | sudo -u postgres psql pulstock

sudo systemctl restart pulstock-api

sudo pm2 start pulstock-web
echo "✅ Restauración completada"
RESTORE_EOF
chmod +x /root/restore.sh
```


---

## Restaurar desde un respaldo cifrado — probado el 24-ago-2026

Este procedimiento se ejecutó de punta a punta contra producción: se cifró un
volcado, se borró el original, se descifró y se restauró en una base
descartable. Las cinco tablas comparadas dieron **exactamente los mismos
conteos** que producción.

### 1. Descifrar

```bash
gpg --batch --passphrase-fd 0 --decrypt     --output /tmp/restore.sql.gz     /var/backups/pulstock/pulstock_AAAAMMDD_HHMM.sql.gz.gpg
```

Pide la contraseña por stdin. Está en `/etc/pulstock-backup.env` **y debería
estar también en un gestor de contraseñas**: si se pierde, todos los respaldos
cifrados son basura irrecuperable.

Verificá que salió bien antes de seguir:

```bash
gzip -t /tmp/restore.sql.gz && echo "archivo integro"
```

### 2. Restaurar en una base descartable, NUNCA sobre producción

```bash
sudo -u postgres psql -c "CREATE DATABASE pulstock_restore OWNER pulstock;"
zcat /tmp/restore.sql.gz | sudo -u postgres psql -d pulstock_restore
```

> **`sudo -u postgres` no es opcional.** El usuario `pulstock` **no tiene
> permiso para crear bases** (`rolcreatedb = f`). Si intentás con él, el
> `CREATE DATABASE` falla, el restore va a una base que no existe y las
> consultas devuelven vacío — parece que el respaldo estaba corrupto cuando el
> problema era el permiso. Pasó en la primera prueba.

### 3. Comparar antes de confiar

```bash
for t in sales_sale catalog_product inventory_stockmove core_tenant; do
  a=$(sudo -u postgres psql -d pulstock -tAc "SELECT count(*) FROM $t")
  b=$(sudo -u postgres psql -d pulstock_restore -tAc "SELECT count(*) FROM $t")
  printf "%-24s prod=%-8s restaurada=%s
" "$t" "$a" "$b"
done
```

### 4. Recién ahí, promover

Si los conteos cuadran y la app arranca contra la base restaurada, se puede
apuntar `DATABASE_URL` a ella o renombrar. **Antes de promover, hacer un
volcado de la base actual**: por rota que esté, puede tener datos de hoy que el
respaldo no.

```bash
sudo -u postgres psql -c "DROP DATABASE pulstock_restore;"   # al terminar la prueba
```

### Cada cuánto conviene hacer esto

Una vez al mes, aunque no pase nada. Un respaldo que nunca se restauró es una
suposición, no un respaldo — y el día que haga falta no es el día de descubrir
que no funcionaba.
