# Pulstock — Setup de emails con Brevo

Guía completa para configurar envío de emails transaccionales desde Pulstock usando [Brevo](https://www.brevo.com/) (ex-Sendinblue).

## Por qué Brevo

- **300 emails/día gratis** (9.000/mes) — sobra para Pulstock en etapa actual
- **Dominio verificado** con SPF/DKIM/DMARC → inboxes primarios, no spam
- **Dashboard de métricas**: aperturas, clicks, rebotes, quejas
- **SMTP simple**: Django funciona out-of-the-box sin librerías extra
- **Lite $25/mes** cuando crezcas: 20k emails/mes

---

## 📋 Checklist — setup inicial (una vez)

### Paso 1 — Crear cuenta Brevo

1. Andá a https://www.brevo.com/ → **Sign up free**
2. Usá el **email corporativo de Pulstock** (no personal)
3. Plan: **Free** (el pricing lo subís después si hace falta)
4. Propósito: **Transactional emails** (NO marketing)
5. Activá **2FA** inmediatamente: Account → Security → Two-factor authentication

### Paso 2 — Verificar dominio `pulstock.cl`

1. Menú lateral: **Senders, Domains & Dedicated IPs** → pestaña **Domains**
2. Click **"Add a Domain"** → escribí `pulstock.cl` → Save
3. Brevo genera 3 registros DNS — los vamos a agregar a Cloudflare

### Paso 3 — Agregar registros en Cloudflare

En https://dash.cloudflare.com → `pulstock.cl` → **DNS** → **Records**, agregá estos 4:

#### SPF (Sender Policy Framework)
Autoriza a Brevo a mandar emails en nombre de `pulstock.cl`.

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| TXT | `@` (o `pulstock.cl`) | `v=spf1 include:spf.brevo.com ~all` | ⚪ DNS only | Auto |

> Si ya tenés un SPF record existente, NO crees otro — extendelo: `v=spf1 include:spf.brevo.com include:otro.com ~all`. Solo puede haber un SPF por dominio.

#### DKIM (DomainKeys Identified Mail)
Brevo firma cada email con esta llave privada; los servidores receptores validan la firma contra esta llave pública.

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| TXT | `mail._domainkey` | `k=rsa; p=<LLAVE-LARGA-QUE-TE-DA-BREVO>` | ⚪ DNS only | Auto |

> El valor exacto lo ves en Brevo en la pantalla del dominio. Es un string largo (1-2 líneas). Copialo **exacto**, incluyendo `k=rsa; p=`.

#### Brevo ownership verification
Prueba que vos controlás el dominio.

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| TXT | `brevo-code` | `brevo-code=<HASH-QUE-TE-DA-BREVO>` | ⚪ DNS only | Auto |

#### DMARC (Domain-based Message Authentication)
Política de qué hacer si un email que dice ser de `pulstock.cl` NO pasa SPF/DKIM (probable phishing).

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:pulstock.admin@gmail.com; fo=1` | ⚪ DNS only | Auto |

> `p=none` = solo reportar (no bloquear). Después de 2 semanas de uso estable, subí a `p=quarantine` y luego a `p=reject` para endurecer.

### Paso 4 — Esperar propagación y validar en Brevo

1. Esperá 15-60 min para que Cloudflare propague
2. En Brevo → Domains → click **"Verify"** en `pulstock.cl`
3. Te marca ✅ SPF / ✅ DKIM / ✅ Ownership cuando estén OK
4. Validá DMARC también en https://mxtoolbox.com/dmarc.aspx

### Paso 5 — Obtener credenciales SMTP

En Brevo → **SMTP & API** → pestaña **SMTP**:

```
SMTP server : smtp-relay.brevo.com
Port        : 587 (TLS) o 465 (SSL)
Login       : <tu_email_brevo>
SMTP key    : xsmtpsib-xxxxxxxxxxxxxxxxxxxxxxxx
```

### Paso 6 — Configurar Senders

En Brevo → **Senders**:

| Sender | Email | Uso |
|--------|-------|-----|
| Pulstock (no-reply) | `no-reply@pulstock.cl` | Emails automáticos (billing, reminders) |
| Pulstock Soporte | `soporte@pulstock.cl` | Soporte manual |
| Pulstock | `hola@pulstock.cl` | Bienvenidas / onboarding |

> Los emails NO tienen que ser buzones reales. Para recibir respuestas, usá [ImprovMX](https://improvmx.com/) gratis → forward a tu Gmail.

### Paso 7 — Actualizar `.env` en el server

```bash
ssh root@65.108.148.200
cd /var/www/pulstock/apps/api
cp .env .env.bak.pre-brevo.$(date +%Y%m%d-%H%M%S)

# Editar .env:
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=<tu_email_brevo>
EMAIL_HOST_PASSWORD=xsmtpsib-xxxxxxxxxxxx
DEFAULT_FROM_EMAIL=Pulstock <no-reply@pulstock.cl>
SERVER_EMAIL=soporte@pulstock.cl

# Reload gunicorn
pkill -HUP -f 'gunicorn api.wsgi'
```

### Paso 8 — Test end-to-end

```bash
cd /var/www/pulstock/apps/api
venv/bin/python manage.py send_test_email tu@gmail.com
```

Si el email llega a tu inbox principal (no spam), todo está OK.

---

## 🧪 Cómo validar que llega a inbox (no spam)

Un email que pasa SPF + DKIM + DMARC + dominio con historia tiene ~99% chance de llegar a inbox. Herramientas:

- **Mail-tester.com**: mandá el test a la dirección random que te den → te da un score 0-10. Objetivo: 9.5+
- **Postmaster Tools de Google**: https://postmaster.google.com/ — stats de reputación de `pulstock.cl`
- **MXToolbox**: https://mxtoolbox.com/SuperTool.aspx → chequear SPF, DKIM, DMARC

---

## 📊 Monitoring de emails

### Brevo dashboard
- **Statistics** → opens, clicks, bounces, spam reports
- **Transactional → Logs** → ver cada email individual con timestamp + status
- Si ves muchos "Soft bounces" → revisá contenido o listas

### Alertas recomendadas
Configurá en Brevo:
- Alerta si **bounce rate > 5%**
- Alerta si **spam reports > 0.1%**
- Alerta si **daily limit > 80%** (te estás acercando al free tier)

---

## 🔧 Troubleshooting

### "Emails no llegan — ni spam"

```bash
# 1. Verificar que SMTP está configurado
ssh root@65.108.148.200
cd /var/www/pulstock/apps/api
venv/bin/python manage.py send_test_email tu@gmail.com

# 2. Ver logs de gunicorn para errores SMTP
tail -50 /var/log/pulstock/gunicorn-error.log | grep -i smtp

# 3. Check dominio en Brevo dashboard → Domains → debe estar "Authenticated"
```

### "Llegan a SPAM"

1. Verificar SPF/DKIM/DMARC con https://mxtoolbox.com/SuperTool.aspx
2. Mail-tester.com score <9 → ver qué flagear
3. Contenido muy comercial → ajustar subject/body
4. Dominio sin historia → mandar gradualmente, no 1000 emails el día 1

### "Error 535 — authentication failed"

SMTP key inválida o revocada. Generá una nueva en Brevo → SMTP → "Generate new key".

### "Daily limit exceeded"

Free tier es 300 emails/día. Si tu volumen crece:
- Upgrade a **Lite $25/mes** (20k/mes)
- O migrar a **Postmark**/**SendGrid** que tienen tiers similares

---

## 📈 Cuando escales (roadmap)

- **>20k emails/mes**: evaluar Postmark ($15/10k), SendGrid Essentials ($19.95/50k)
- **Cross-channel** (SMS, WhatsApp): Brevo tiene todo integrado
- **Campañas marketing**: Brevo Marketing ($25/mes) con list management, A/B testing
- **Dedicated IP**: requerido si emails >50k/mes para proteger reputación

---

## 🔐 Seguridad

- **2FA en Brevo**: obligatorio. Alguien con acceso puede mandar spam con tu dominio.
- **SMTP key rotación**: cada 6-12 meses generá nueva key y actualizá `.env`.
- **DMARC strict** (`p=reject`) tras 2-4 semanas estable.
- **Rate limit en Django**: ya existe (20/hr sensitive action) — protege de ataque que spamee tu API para mandar emails.
