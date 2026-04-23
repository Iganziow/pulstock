# Pulstock — Guía de monitoring y alertas

Esta guía lista los **monitores externos** que recomiendo configurar en tu servicio de monitoring (UptimeRobot, Better Uptime, Pingdom, etc.) y lo que YA está implementado server-side para que los monitors puedan chequearlo.

---

## 🎯 Monitores externos a configurar

### 1. Liveness básico (crítico, 1–5 min)

| Monitor | URL | Método | Espera | Qué detecta |
|---------|-----|--------|--------|-------------|
| API liveness | `https://api.pulstock.cl/api/core/health/` | GET | 200 | Gunicorn down, nginx down, SSL cert expirado |
| App liveness | `https://app.pulstock.cl/` | GET | 200 | PM2/Next down, build roto |
| Landing | `https://pulstock.cl/` | GET | 200 | idem app |

**Frecuencia**: cada 1-5 min. Alert si falla 2 veces seguidas.

### 2. Deep health (alto, 5–10 min)

| Monitor | URL | Método | Espera | Qué detecta |
|---------|-----|--------|--------|-------------|
| Deep health | `https://api.pulstock.cl/api/core/health/deep/` | GET | 200 con `{"status": "ok"}` | **DB, Redis, crons stale/failed, disco <10%** |

**Frecuencia**: cada 5-10 min.
**Opcional**: si querés ver el detalle, usá `?token=<DEEP_HEALTH_TOKEN>` (configurado en `.env`).

### 3. SSL cert expiry (medio)

La mayoría de monitores tienen esto integrado — activá alertas de **SSL certificate** para los 4 dominios, que avisen con **14 días** de anticipación. Certbot renueva solo cada 60 días, pero esto es tu red de seguridad.

### 4. Cron heartbeat (crítico para billing)

El endpoint `/api/core/health/deep/` ya reporta cron tasks stale. Estos son los `task_name` registrados:

| Task | Max age | Corre |
|------|---------|-------|
| `billing.process_renewals` | 90 min | cada hora :00 |
| `billing.retry_payments` | 90 min | cada hora :15 |
| `billing.suspend_overdue` | 90 min | cada hora :30 |
| `billing.send_reminders` | 36 h | diario 09:00 |
| `billing.expire_trials` | 36 h | diario 02:00 |
| `printing.cleanup_jobs` | 36 h | diario 03:30 |

Si alguno sobrepasa su `max_age`, el deep health cambia a `degraded` y el monitor alerta.

---

## 📊 Dashboard completo sugerido (Better Uptime / Grafana)

Si querés algo más rico que UptimeRobot, te sirven estos checks:

### Grupo "Servicio público"
- ✅ API health (https://api.pulstock.cl/api/core/health/)
- ✅ App dashboard (https://app.pulstock.cl/)
- ✅ Landing (https://pulstock.cl/)
- ✅ SSL expiry (los 4 dominios)

### Grupo "Interno"
- ✅ Deep health (https://api.pulstock.cl/api/core/health/deep/?token=X) — DB, Redis, crons, disk
- ⚠️ Opcional: crea un endpoint de heartbeat para cada cron que quieras monitorear individualmente

### Grupo "Pagos"
- Webhook test Flow.cl (tira 400 sin token, valida que el endpoint responde)
- Puedes manualmente verificar `billing.process_renewals.last_run_at` en DB

---

## 🔔 Alertas críticas (acción humana inmediata)

| Alerta | Acción |
|--------|--------|
| API liveness falla 2x seguidas | SSH al server, revisar `systemctl status nginx` y `ps aux \| grep gunicorn` |
| Deep health = "down" (DB falla) | Revisar `systemctl status postgresql` y logs |
| Deep health = "degraded" por crons | `tail /var/log/pulstock/billing-cron.log` |
| SSL cert a 7 días de expirar | Ejecutar `certbot renew` manualmente |
| Disco <10% libre | SSH, revisar `/var/log/` y limpiar |

---

## 🛠️ Implementado en código

### `CronHeartbeat` model (core/models.py)
Tabla que registra última ejecución exitosa de cada cron. Schema:
```sql
task_name           VARCHAR(100) PRIMARY KEY
last_run_at         TIMESTAMPTZ  (auto_now)
last_duration_s     FLOAT
last_result         VARCHAR(20)  -- "ok" | "failed" | "running"
last_error          VARCHAR(500)
expected_max_age_minutes INT     -- cuándo considerar stale
```

### `cron_wrapper` context manager (core/cron_utils.py)
Todo management command de cron lo usa:
```python
with cron_wrapper("billing.process_renewals", max_age_min=90):
    # ... tu lógica
```
Registra heartbeat automáticamente al terminar (OK o failed).

### `DeepHealthView` endpoint (core/urls.py)
- `GET /api/core/health/deep/` → `{"status": "ok|degraded|down"}`
- `GET /api/core/health/deep/?token=<SECRET>` → detalles completos

**Verifica**:
- DB (query + latency)
- Redis (ping + latency)
- Cron heartbeats (stale / failed)
- Disk space (<10% warn, <5% critical)

---

## 🚨 Checklist de deploy del sistema de monitoring

- [x] Modelo `CronHeartbeat` + migración
- [x] `cron_wrapper` en los 6 management commands
- [x] Endpoint `/api/core/health/deep/`
- [x] Settings: `DEEP_HEALTH_TOKEN` opcional
- [ ] Setear `DEEP_HEALTH_TOKEN=<valor-aleatorio>` en `.env` de prod
- [ ] Configurar monitor externo con 3 URLs base (api, app, landing)
- [ ] Configurar monitor externo con deep health
- [ ] Configurar alertas SSL 14d antes de expirar

---

## 🛠️ Setup paso a paso (1 día de trabajo total)

### A) Sentry — tracking de errores Python + JS (15 min)

El SDK ya está configurado en código. Falta solo el DSN.

**Backend (Django)**:

1. Crear cuenta en [sentry.io](https://sentry.io) (free: 5000 errors/mes — sobra).
2. Crear proyecto tipo **Django**. Te da un DSN así: `https://abc123@o456.ingest.sentry.io/789`.
3. SSH al server:
   ```bash
   ssh ignacio@65.108.148.200
   echo "SENTRY_DSN=https://abc123@o456.ingest.sentry.io/789" >> /var/www/pulstock/apps/api/.env
   echo "SENTRY_ENV=production" >> /var/www/pulstock/apps/api/.env
   pdeploy-api    # reload gunicorn con la nueva config
   ```
4. Para verificar que anda, en el shell de Django:
   ```bash
   pmanage shell
   >>> 1 / 0      # error a propósito
   ```
   Debería aparecer en el dashboard de Sentry en <1 minuto.

**Frontend (Next.js)**:

1. En el mismo proyecto Sentry, crear una segunda **plataforma** tipo **Next.js**. Te da otro DSN.
2. Crear un **Auth Token** para upload de source maps: Sentry → Settings → Account → Auth Tokens → Create New Token (scopes: `project:releases`, `project:write`).
3. SSH:
   ```bash
   ssh ignacio@65.108.148.200
   cd /var/www/pulstock/apps/web
   echo "NEXT_PUBLIC_SENTRY_DSN=https://xyz789@o456.ingest.sentry.io/012" >> .env.local
   echo "SENTRY_DSN=https://xyz789@o456.ingest.sentry.io/012" >> .env.local
   echo "SENTRY_AUTH_TOKEN=sntrys_xxx..." >> .env.local
   echo "SENTRY_ORG=tu-org-slug" >> .env.local
   echo "SENTRY_PROJECT=pulstock-web" >> .env.local
   pdeploy-web    # rebuild con sourcemaps
   ```
4. Para verificar: navegar a `https://pulstock.cl/?test_sentry=throw` — el frontend lanza un error de prueba (necesitarías agregar la trampa antes; o simplemente romper algo manualmente).

### B) UptimeRobot — uptime monitoring (10 min)

1. Crear cuenta en [uptimerobot.com](https://uptimerobot.com) (free: 50 monitors, 5 min interval).
2. Crear estos **5 monitors** (tipo HTTPS, intervalo 5 min):

   | Nombre | URL |
   |---|---|
   | Pulstock — Landing | `https://pulstock.cl` |
   | Pulstock — App | `https://pulstock.cl/login` |
   | Pulstock — API | `https://api.pulstock.cl/api/core/health/` |
   | Pulstock — Deep health | `https://api.pulstock.cl/api/core/health/deep/` |
   | Pulstock — Agente .exe (descarga) | `https://pulstock.cl/agent/PulstockAgent.exe` |

3. Para cada monitor: en **Alert Contacts**, agregar tu email y/o el bot de Telegram (siguiente sección).
4. **SSL Monitoring**: Account → Settings → activar "SSL Cert Expiry" — alerta 14 días antes de vencer.

### C) Bot de Telegram para alertas (5 min)

UptimeRobot tiene integración nativa con Telegram. Más simple que mantener tu propio bot.

1. **Crear el bot**:
   - Abrir Telegram, buscar `@BotFather`.
   - Mandarle `/newbot`, seguir instrucciones.
   - Te da un **token** del bot (algo así: `123456:ABC-DEF...`).

2. **Crear el grupo de alertas** (recomendado vs DM directo):
   - Crear grupo en Telegram (ej: "Pulstock Alerts").
   - Agregar a tu bot al grupo (search por su username).
   - Mandar un mensaje cualquiera al grupo (ej: "test").
   - Visitar en el browser: `https://api.telegram.org/bot<TU-TOKEN>/getUpdates` →
     copiar el `chat.id` (ej: `-1001234567890`, los grupos empiezan con `-`).

3. **Conectar a UptimeRobot**:
   - UptimeRobot → My Settings → Alert Contacts → Add Alert Contact.
   - Type: **Telegram**.
   - Pegar el bot token + chat_id.
   - Asignar este contact a tus monitors.

4. **Probar**: pausar un monitor 1 minuto y reactivarlo — debería llegar alerta DOWN/UP a Telegram en <2 min.

### D) Setup adicional opcional

**Notificaciones a tu propio script** (si querés alertas custom desde el server, no solo del monitor externo):

```bash
# Crear ~/notify-telegram.sh en el server
cat > ~/notify-telegram.sh <<'EOF'
#!/usr/bin/env bash
# Uso: ~/notify-telegram.sh "mensaje"
# Requiere ~/.telegram_creds con: BOT_TOKEN=... CHAT_ID=...
source ~/.telegram_creds
curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
  -d "chat_id=$CHAT_ID" \
  -d "text=🚨 [Pulstock] $1" \
  -d "parse_mode=HTML" > /dev/null
EOF
chmod +x ~/notify-telegram.sh

# Guardar credenciales
echo 'BOT_TOKEN=123456:ABC-DEF...' >> ~/.telegram_creds
echo 'CHAT_ID=-1001234567890' >> ~/.telegram_creds
chmod 600 ~/.telegram_creds

# Probar
~/notify-telegram.sh "Test desde el server"
```

Lo podés llamar desde cualquier cron, pre-deploy hook, etc.

---

## 📉 Cuotas free relevantes

| Servicio | Free tier | Vuestro estimado |
|---|---|---|
| Sentry | 5000 errors/mes, 1 user, 30d retention | <100 errors/mes en piloto → sobra |
| UptimeRobot | 50 monitors, 5 min interval | usamos 5 → sobra |
| Telegram | ilimitado | — |

Cuando crezcas a 10+ clientes activos, el free tier de Sentry se queda corto. Plan Team: $26/mes (50k errors).

---

## 📈 Futuro — cuando crezcas a 50+ clientes

1. **Logs estructurados** → agregador tipo Grafana Loki o Elastic.
2. **Prometheus + Grafana** para métricas custom (latencia API, errores 5xx, cobros/hora).
3. **PagerDuty/Opsgenie** para on-call rotation con escalación.
4. **Statuspage** público (statuspage.io) para mostrar uptime histórico a clientes.
