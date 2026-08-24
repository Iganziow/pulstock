#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# Pulstock — respaldo diario de la base
#
# Copia canonica de /var/backups/pulstock/backup.sh. Se versiona aca porque
# el original vive solo en el servidor: si se pierde ese disco, se pierde el
# script que servia para recuperarse de perder ese disco.
#
# Que hace, en orden:
#   1. Vuelca la base y la comprime
#   2. La CIFRA  (el archivo sale del servidor, no puede salir en claro)
#   3. La sube a Backblaze B2  (capa gratuita, 10 GB, sin tarjeta)
#   4. Deja un latido para que /health/deep/ sepa que corrio
#   5. Borra las copias locales viejas
#
# Por que cifrado: el volcado tiene datos de clientes. Subirlo en claro a un
# tercero es exponerlos, y la Ley 21.719 entra en vigencia plena el 1-dic-2026.
# Cifrado, el proveedor solo guarda un bloque opaco.
#
# LA CLAVE DE CIFRADO NO ESTA EN ESTE ARCHIVO Y NO DEBE ESTARLO.
# Vive en /etc/pulstock-backup.env, con permisos 600 y dueño root.
# Si se pierde esa clave, los respaldos cifrados son basura irrecuperable:
# hay que guardarla ADEMAS en otro lado (gestor de contraseñas).
# ══════════════════════════════════════════════════════════════════════
set -uo pipefail

BACKUP_DIR=/var/backups/pulstock
API_DIR=/var/www/pulstock/apps/api
DATE=$(date +%Y%m%d_%H%M)
FILENAME="pulstock_${DATE}.sql.gz"
DIAS_LOCALES=14
INICIO=$(date +%s)

# Configuración sensible, fuera del script y fuera del repositorio.
#   PULSTOCK_BACKUP_PASSPHRASE=...
#   B2_KEY_ID=...
#   B2_APP_KEY=...
#   B2_BUCKET=...
[ -f /etc/pulstock-backup.env ] && source /etc/pulstock-backup.env

latido() {  # latido "<mensaje de error o vacio>"
    local dur=$(( $(date +%s) - INICIO ))
    cd "$API_DIR" 2>/dev/null || return 0
    if [ -n "$1" ]; then
        venv/bin/python manage.py registrar_heartbeat backup.diario \
            --duracion "$dur" --fallo "$1" >/dev/null 2>&1
    else
        venv/bin/python manage.py registrar_heartbeat backup.diario \
            --duracion "$dur" >/dev/null 2>&1
    fi
}

morir() {
    echo "$(date): FALLO — $1" >> "$BACKUP_DIR/backup.log"
    latido "$1"
    exit 1
}

# ── 1. Volcado ────────────────────────────────────────────────────────
# NO se hace `source` del .env.
#
# Ese archivo tiene valores con espacios sin comillas --DEFAULT_FROM_EMAIL,
# por ejemplo-- que hacen que bash aborte a media lectura. El script viejo
# funcionaba por suerte y no por diseño: DATABASE_URL esta en la linea 4 y el
# error aparece en la 31. Reordenar el archivo habria roto el respaldo sin
# que nada avisara.
DB_URL=$(grep -m1 '^DATABASE_URL=' "$API_DIR/.env" | cut -d= -f2-)
# Quitar comillas envolventes si las tuviera, con expansion de parametros.
DB_URL="${DB_URL%\"}" ; DB_URL="${DB_URL#\"}"
DB_URL="${DB_URL%\'}" ; DB_URL="${DB_URL#\'}"
DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

export PGPASSWORD="$DB_PASS"
# El pipefail de arriba hace que un pg_dump fallido no pase inadvertido por
# culpa de que gzip devuelve 0 igual.
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" \
    | gzip > "$BACKUP_DIR/$FILENAME" || morir "pg_dump fallo"
unset PGPASSWORD

[ -s "$BACKUP_DIR/$FILENAME" ] || morir "el volcado quedo vacio"
TAM=$(du -h "$BACKUP_DIR/$FILENAME" | cut -f1)

# ── 2. Cifrado ────────────────────────────────────────────────────────
if [ -n "${PULSTOCK_BACKUP_PASSPHRASE:-}" ]; then
    echo "$PULSTOCK_BACKUP_PASSPHRASE" | gpg --batch --yes --quiet \
        --passphrase-fd 0 --symmetric --cipher-algo AES256 \
        --output "$BACKUP_DIR/$FILENAME.gpg" "$BACKUP_DIR/$FILENAME" \
        || morir "el cifrado fallo"
    SUBIR="$BACKUP_DIR/$FILENAME.gpg"
else
    # Sin clave configurada NO se sube nada. Es preferible quedarse sin copia
    # externa a mandar datos de clientes en claro a un tercero.
    SUBIR=""
    echo "$(date): AVISO — sin clave de cifrado, no se sube nada" >> "$BACKUP_DIR/backup.log"
fi

# ── 3. Copia fuera del servidor ───────────────────────────────────────
SUBIDO="no"
if [ -n "$SUBIR" ] && [ -n "${B2_KEY_ID:-}" ] && [ -n "${B2_APP_KEY:-}" ]; then
    AUTH=$(curl -s -u "${B2_KEY_ID}:${B2_APP_KEY}" \
        https://api.backblazeb2.com/b2api/v3/b2_authorize_account)
    TOKEN=$(echo "$AUTH" | grep -o '"authorizationToken":"[^"]*' | head -1 | cut -d'"' -f4)
    API=$(echo "$AUTH" | grep -o '"apiUrl":"[^"]*' | head -1 | cut -d'"' -f4)

    if [ -n "$TOKEN" ] && [ -n "$API" ]; then
        UP=$(curl -s -H "Authorization: $TOKEN" \
            -d "{\"bucketId\":\"${B2_BUCKET_ID}\"}" \
            "$API/b2api/v3/b2_get_upload_url")
        UP_URL=$(echo "$UP" | grep -o '"uploadUrl":"[^"]*' | head -1 | cut -d'"' -f4)
        UP_TOKEN=$(echo "$UP" | grep -o '"authorizationToken":"[^"]*' | head -1 | cut -d'"' -f4)
        SHA=$(sha1sum "$SUBIR" | cut -d' ' -f1)

        if [ -n "$UP_URL" ]; then
            RESP=$(curl -s -H "Authorization: $UP_TOKEN" \
                -H "X-Bz-File-Name: $(basename "$SUBIR")" \
                -H "Content-Type: application/octet-stream" \
                -H "X-Bz-Content-Sha1: $SHA" \
                --data-binary "@$SUBIR" "$UP_URL")
            echo "$RESP" | grep -q '"fileId"' && SUBIDO="si"
        fi
    fi
    [ "$SUBIDO" = "no" ] && echo "$(date): AVISO — no se pudo subir a B2" >> "$BACKUP_DIR/backup.log"
fi

# ── 4. Constancia ─────────────────────────────────────────────────────
echo "$(date): OK — $FILENAME ($TAM), externa=$SUBIDO" >> "$BACKUP_DIR/backup.log"

# Una copia que solo esta en el mismo disco que la base NO es un respaldo:
# el incendio, el ransomware y el borrado se llevan las dos a la vez. Si la
# subida fallo, el latido queda como fallido y /health/deep/ lo marca.
if [ "$SUBIDO" = "si" ]; then
    latido ""
else
    latido "respaldo local OK pero SIN copia fuera del servidor"
fi

# ── 5. Limpieza ───────────────────────────────────────────────────────
find "$BACKUP_DIR" -name 'pulstock_*.sql.gz'     -mtime +$DIAS_LOCALES -delete
find "$BACKUP_DIR" -name 'pulstock_*.sql.gz.gpg' -mtime +$DIAS_LOCALES -delete
