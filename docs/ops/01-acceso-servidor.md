# 1. Acceso al servidor

## Conectar por SSH

```bash
ssh ignacio@65.108.148.200
```

El usuario es `ignacio`. **`root` no tiene login por SSH**, así que cualquier comando que necesite privilegios va con `sudo`.

Si te pide contraseña usa la que guardaste. Si ya configuraste tu llave SSH (`~/.ssh/id_ed25519.pub` en `authorized_keys` del servidor), entra sin password.

## Configurar acceso sin password (recomendado)

Desde tu máquina local (una sola vez):

```bash
# 1. Ver tu llave pública (si no tienes, crea con: ssh-keygen -t ed25519)
cat ~/.ssh/id_ed25519.pub

# 2. Copiar al servidor (reemplaza TU_LLAVE_PUBLICA por lo que imprimió el paso 1)
ssh ignacio@65.108.148.200 "mkdir -p ~/.ssh && echo 'TU_LLAVE_PUBLICA' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
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
| Tareas programadas | `/etc/cron.d/pulstock` **y** `crontab -l` de `ignacio` |
| Servicio del backend | `pulstock-api.service` (systemd, corre como root) |
| Frontend | PM2 **como root** → todo comando pm2 lleva `sudo` |


> **Las tareas programadas están en dos lugares.** `/etc/cron.d/pulstock` tiene
> facturación, trials y alertas. El crontab personal de `ignacio` tiene el
> pipeline del forecast **y el backup diario** — y ese no está en el
> repositorio. Copia de respaldo en [`pulstock-crontab.txt`](pulstock-crontab.txt).

## Salir del servidor

```bash
exit
# o Ctrl+D
```
