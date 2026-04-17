# 1. Acceso al servidor

## Conectar por SSH

```bash
ssh root@65.108.148.200
```

Si te pide password usa el que guardaste. Si ya configuraste tu llave SSH (`~/.ssh/id_ed25519.pub` en `authorized_keys` del servidor), entra sin password.

## Configurar acceso sin password (recomendado)

Desde tu máquina local (una sola vez):

```bash
# 1. Ver tu llave pública (si no tienes, crea con: ssh-keygen -t ed25519)
cat ~/.ssh/id_ed25519.pub

# 2. Copiar al servidor
ssh root@65.108.148.200 "mkdir -p ~/.ssh && echo 'TU_LLAVE_PUBLICA' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

## Ubicaciones importantes

| Qué | Dónde |
|-----|-------|
| Código fuente | `/var/www/pulstock/` |
| Backend | `/var/www/pulstock/apps/api/` |
| Frontend | `/var/www/pulstock/apps/web/` |
| Virtualenv Python | `/var/www/pulstock/apps/api/venv/` |
| Variables de entorno | `/var/www/pulstock/apps/api/.env` |
| Logs Gunicorn | `/var/log/pulstock/gunicorn-*.log` |
| Logs Nginx | `/var/log/nginx/*.log` |
| Backups | `/var/backups/pulstock/` |
| Config Nginx | `/etc/nginx/sites-enabled/pulstock` |
| Crontabs | `/etc/cron.d/pulstock-trials` + user crontab |

## Salir del servidor

```bash
exit
# o Ctrl+D
```
