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

## 📈 Futuro — cuando crezcas

Cuando tengas 10+ clientes:

1. **Sentry** para tracking de errores Python + JS — integración con 5 min de trabajo
2. **Logs estructurados** → agregador tipo Grafana Loki o Elastic
3. **Prometheus + Grafana** para métricas custom (latencia API, errores 5xx, cobros/hora)
4. **PagerDuty/Opsgenie** para on-call rotation

Por ahora con UptimeRobot + alertas email alcanza.
