# Guía de despliegue — Pulstock

**Arquitectura:**
- Frontend (Next.js) → **Vercel**
- Backend (Django + Celery + Redis + PostgreSQL) → **Hetzner**
- Dominio: `pulstock.cl` (DNS: dnsmisitio.net)

---

## 1. DNS — Configurar en dnsmisitio.net

Ingresar al panel de dnsmisitio.net y agregar estos registros para `pulstock.cl`:

| Tipo  | Nombre            | Valor                  | TTL  |
|-------|-------------------|------------------------|------|
| A     | `@` (raíz)        | `76.76.21.21`          | 3600 |
| CNAME | `www`             | `cname.vercel-dns.com` | 3600 |
| A     | `api`             | `<IP_HETZNER>`         | 3600 |

> **Notas:**
> - `76.76.21.21` es la IP de Vercel para dominios apex
> - `<IP_HETZNER>` es la IP pública del servidor Hetzner (se obtiene en la consola de Hetzner Cloud)
> - Los cambios DNS pueden demorar hasta 24h en propagarse

---

## 2. Hetzner — Configuración inicial del servidor

### Servidor recomendado
- **CPX21** (3 vCPU, 4 GB RAM, 80 GB SSD) — suficiente para empezar
- **OS:** Ubuntu 24.04 LTS
- **Región:** Falkenstein (EU) o Helsinki

### Setup inicial (ejecutar como root)

```bash
# Actualizar sistema
apt update && apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# Crear usuario de deploy
useradd -m -s /bin/bash deploy
usermod -aG docker deploy

# Clonar el repo
su - deploy
git clone <URL_REPO> /home/deploy/pulstock
cd /home/deploy/pulstock

# Configurar variables de entorno
cp .env.production.example .env.production
nano .env.production   # completar todos los valores
```

### SSL — Obtener certificado (primera vez)

Antes de levantar el stack completo, obtener el certificado SSL:

```bash
# Levantar solo nginx en modo HTTP (sin SSL todavía)
docker compose up -d nginx

# Solicitar certificado
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d api.pulstock.cl \
  --email tu@email.com \
  --agree-tos --no-eff-email

# Verificar que se obtuvo el certificado
ls /etc/letsencrypt/live/api.pulstock.cl/

# Levantar el stack completo
docker compose up -d
```

### Levantar el stack completo

```bash
docker compose up -d
docker compose logs -f api   # verificar que levantó bien
```

### Crear superusuario Django (primera vez)

```bash
docker compose exec api python manage.py createsuperuser
```

### Renovación automática de SSL

Agregar a crontab del usuario `deploy`:

```bash
crontab -e
# Agregar:
0 3 * * * cd /home/deploy/pulstock && docker compose run --rm certbot renew --quiet && docker compose exec nginx nginx -s reload
```

---

## 3. Vercel — Configuración

### Conectar el repositorio

1. Ir a [vercel.com](https://vercel.com) → New Project
2. Importar el repositorio de GitHub
3. Vercel detecta automáticamente el `vercel.json` → root directory `apps/web`
4. En **"Environment Variables"**, agregar:

| Variable              | Valor                          | Entornos         |
|-----------------------|--------------------------------|------------------|
| `NEXT_PUBLIC_API_URL` | `https://api.pulstock.cl/api`  | Production       |
| `NEXT_PUBLIC_API_URL` | `https://api.pulstock.cl/api`  | Preview          |

5. Click en **Deploy**

### Agregar dominio personalizado

1. En el proyecto de Vercel → **Settings → Domains**
2. Agregar `pulstock.cl` y `www.pulstock.cl`
3. Vercel verificará automáticamente los registros DNS (ya configurados en paso 1)

---

## 4. Deploys futuros

### Backend (Hetzner)
```bash
# En el servidor Hetzner
cd /home/deploy/pulstock
./deploy.sh
```

### Frontend (Vercel)
El frontend **se despliega automáticamente** cuando se hace push a `main` en GitHub. No requiere ninguna acción manual.

---

## 5. Comandos útiles en producción

```bash
# Ver logs de la API
docker compose logs api -f --tail=100

# Ver logs de Celery
docker compose logs celery-worker -f

# Reiniciar solo la API (sin downtime de DB/Redis)
docker compose restart api

# Ejecutar comando Django
docker compose exec api python manage.py <comando>

# Backup de la base de datos
docker compose exec db pg_dump -U pulstock pulstock > backup_$(date +%Y%m%d).sql

# Estado de todos los servicios
docker compose ps
```

---

## 6. Variables de entorno críticas (resumen)

| Variable | Dónde configurar | Notas |
|---|---|---|
| `DJANGO_SECRET_KEY` | `.env.production` en Hetzner | Generar aleatoriamente |
| `DATABASE_URL` | `.env.production` en Hetzner | Apunta al contenedor `db` |
| `WEB_ORIGIN` | `.env.production` en Hetzner | `https://pulstock.cl,https://www.pulstock.cl` |
| `FLOW_API_KEY` / `FLOW_SECRET_KEY` | `.env.production` en Hetzner | Credenciales Flow.cl |
| `EMAIL_HOST_PASSWORD` | `.env.production` en Hetzner | App password de Gmail |
| `NEXT_PUBLIC_API_URL` | Dashboard de Vercel | `https://api.pulstock.cl/api` |
