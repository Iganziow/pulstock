"""
billing/tasks.py
===============
Tareas Celery para el ciclo de vida de suscripciones.

Requiere Celery + Redis.
CELERY_BROKER_URL y CELERY_BEAT_SCHEDULE están configurados en settings.py.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

# Intentamos importar Celery — si no está disponible el módulo funciona igual
# como funciones normales (útil para desarrollo sin Redis)
try:
    from celery import shared_task
    CELERY_AVAILABLE = True
except ImportError:
    # Fallback: decorator que simplemente ejecuta la función
    def shared_task(func):
        return func
    CELERY_AVAILABLE = False


# ─────────────────────────────────────────────────────────────
# TASK 1: Procesar renovaciones (cobrar planes vencidos)
# ─────────────────────────────────────────────────────────────
@shared_task(name="billing.tasks.process_renewals", bind=True, max_retries=3,
             soft_time_limit=300, time_limit=360)
def process_renewals(self):
    """
    Corre cada hora. Busca suscripciones cuyo período venció
    y que NO son gratuitas, e inicia el cobro.
    """
    from django.conf import settings as dj_settings
    from .models import Subscription, Plan
    from .services import create_invoice, register_payment_failure
    from .gateway import charge_subscription

    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    now = timezone.now()
    due = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        current_period_end__lte=now,
    ).exclude(tenant__slug__in=lifetime_slugs).select_related("tenant", "plan")

    processed = 0
    for sub in due:
        try:
            invoice = create_invoice(sub)
            result  = charge_subscription(sub, invoice)

            if result["success"]:
                from .services import activate_period
                activate_period(sub, invoice)
                logger.info("Renovación exitosa: tenant=%s", sub.tenant_id)
            else:
                register_payment_failure(
                    sub, invoice,
                    error_msg=result.get("error", ""),
                    raw=result.get("raw", {}),
                )
            processed += 1
        except Exception as exc:
            logger.error("Error procesando renovación tenant=%s: %s", sub.tenant_id, exc)

    logger.info("process_renewals: %d suscripciones procesadas", processed)
    return {"processed": processed}


# ─────────────────────────────────────────────────────────────
# TASK 2: Enviar recordatorios de pago
# ─────────────────────────────────────────────────────────────
@shared_task(name="billing.tasks.send_payment_reminders", bind=True,
             max_retries=3, autoretry_for=(Exception,),
             retry_backoff=True, retry_backoff_max=600,
             soft_time_limit=120, time_limit=180)
def send_payment_reminders(self):
    """
    Corre diariamente a las 9am.
    Envía emails de aviso 7, 3 y 1 día antes del vencimiento.
    También avisa cuando el trial está por terminar.
    """
    from .models import Subscription, Plan

    now  = timezone.now()
    sent = 0

    # ── Recordatorios de trial por vencer ──
    trial_subs = Subscription.objects.filter(
        status=Subscription.Status.TRIALING,
    ).select_related("tenant", "plan")

    for sub in trial_subs:
        if not sub.trial_ends_at:
            continue
        days_left = (sub.trial_ends_at - now).days

        if days_left <= 7 and not sub.notified_7_days:
            _send_trial_reminder(sub, days_left)
            sub.notified_7_days = True
            sub.save(update_fields=["notified_7_days"])
            sent += 1
        elif days_left <= 3 and not sub.notified_3_days:
            _send_trial_reminder(sub, days_left)
            sub.notified_3_days = True
            sub.save(update_fields=["notified_3_days"])
            sent += 1
        elif days_left <= 1 and not sub.notified_1_day:
            _send_trial_reminder(sub, days_left)
            sub.notified_1_day = True
            sub.save(update_fields=["notified_1_day"])
            sent += 1

    # ── Recordatorios de renovación próxima ──
    active_subs = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
    ).select_related("tenant", "plan")

    for sub in active_subs:
        if not sub.current_period_end:
            continue
        days_left = (sub.current_period_end - now).days

        if days_left <= 7 and not sub.notified_7_days:
            _send_renewal_reminder(sub, days_left)
            sub.notified_7_days = True
            sub.save(update_fields=["notified_7_days"])
            sent += 1
        elif days_left <= 3 and not sub.notified_3_days:
            _send_renewal_reminder(sub, days_left)
            sub.notified_3_days = True
            sub.save(update_fields=["notified_3_days"])
            sent += 1
        elif days_left <= 1 and not sub.notified_1_day:
            _send_renewal_reminder(sub, days_left)
            sub.notified_1_day = True
            sub.save(update_fields=["notified_1_day"])
            sent += 1

    # ── Aviso de pago fallido (past_due) ──
    past_due_subs = Subscription.objects.filter(
        status=Subscription.Status.PAST_DUE,
        notified_past_due=False,
    ).select_related("tenant", "plan")

    for sub in past_due_subs:
        _send_payment_failed_notice(sub)
        sub.notified_past_due = True
        sub.save(update_fields=["notified_past_due"])
        sent += 1

    logger.info("send_payment_reminders: %d emails enviados", sent)
    return {"sent": sent}


# ─────────────────────────────────────────────────────────────
# TASK 3: Suspender suscripciones past_due sin pagar
# ─────────────────────────────────────────────────────────────
@shared_task(name="billing.tasks.suspend_overdue_subscriptions", bind=True,
             max_retries=3, autoretry_for=(Exception,),
             retry_backoff=True, retry_backoff_max=600,
             soft_time_limit=120, time_limit=180)
def suspend_overdue_subscriptions(self):
    """
    Corre cada hora. Si una suscripción está en past_due
    y ya pasaron los días de gracia (3), la suspende.
    """
    from django.conf import settings as dj_settings
    from .models import Subscription
    from .services import GRACE_PERIOD_DAYS, RETRY_SCHEDULE

    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    now = timezone.now()
    suspended_count = 0

    past_due = Subscription.objects.filter(
        status=Subscription.Status.PAST_DUE,
    ).exclude(tenant__slug__in=lifetime_slugs).select_related("tenant", "plan")

    for sub in past_due:
        # Calcular cuándo se debe suspender
        # Referencia: cuándo terminó el período legítimo
        # NO usar updated_at (se toca en cada save, extiende la gracia infinitamente)
        # Preferir current_period_end; fallback a created_at si falta.
        reference = sub.current_period_end or sub.created_at
        grace_ends = reference + timedelta(days=GRACE_PERIOD_DAYS)

        if now >= grace_ends and sub.payment_retry_count >= len(RETRY_SCHEDULE):
            sub.status       = Subscription.Status.SUSPENDED
            sub.suspended_at = now
            sub.save(update_fields=["status", "suspended_at"])
            _send_suspension_notice(sub)
            suspended_count += 1
            logger.warning("Suscripción suspendida: tenant=%s", sub.tenant_id)

    logger.info("suspend_overdue: %d suscripciones suspendidas", suspended_count)
    return {"suspended": suspended_count}


# ─────────────────────────────────────────────────────────────
# TASK 4: Reintentar cobros fallidos
# ─────────────────────────────────────────────────────────────
@shared_task(name="billing.tasks.retry_failed_payments", bind=True, max_retries=3,
             soft_time_limit=300, time_limit=360)
def retry_failed_payments(self):
    """
    Corre cada hora. Reintenta cobros según el schedule [1, 3, 7] días.
    """
    from django.conf import settings as dj_settings
    from .models import Subscription, Invoice
    from .services import create_invoice, register_payment_failure, activate_period
    from .gateway import charge_subscription

    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    now = timezone.now()
    retried = 0

    to_retry = Subscription.objects.filter(
        status=Subscription.Status.PAST_DUE,
        next_retry_at__lte=now,
        next_retry_at__isnull=False,
    ).exclude(tenant__slug__in=lifetime_slugs).select_related("tenant", "plan")

    for sub in to_retry:
        try:
            invoice = create_invoice(sub)
            result  = charge_subscription(sub, invoice)

            if result["success"]:
                activate_period(sub, invoice)
                _send_payment_recovered_notice(sub)
                logger.info("Reintento exitoso: tenant=%s", sub.tenant_id)
            else:
                register_payment_failure(
                    sub, invoice,
                    error_msg=result.get("error", ""),
                    raw=result.get("raw", {}),
                )
            retried += 1
        except Exception as exc:
            logger.error("Error en reintento tenant=%s: %s", sub.tenant_id, exc)

    logger.info("retry_failed_payments: %d reintentos procesados", retried)
    return {"retried": retried}


# ─────────────────────────────────────────────────────────────
# TASK 5: Convertir trials vencidos
# ─────────────────────────────────────────────────────────────
@shared_task(name="billing.tasks.expire_trials", bind=True,
             max_retries=3, autoretry_for=(Exception,),
             retry_backoff=True, retry_backoff_max=600,
             soft_time_limit=300, time_limit=360)
def expire_trials(self):
    """
    Corre diariamente. Los trials vencidos sin método de pago
    pasan a FREE. Los que sí tienen método de pago, se cobran.
    """
    from django.conf import settings as dj_settings
    from .models import Subscription, Plan
    from .services import change_plan, create_invoice, activate_period, register_payment_failure
    from .gateway import charge_subscription

    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    now = timezone.now()
    expired = Subscription.objects.filter(
        status=Subscription.Status.TRIALING,
        trial_ends_at__lte=now,
    ).exclude(tenant__slug__in=lifetime_slugs).select_related("tenant", "plan")

    converted = 0
    for sub in expired:
        # Intentar cobrar el primer período
        invoice = create_invoice(sub)
        result  = charge_subscription(sub, invoice)

        if result["success"]:
            activate_period(sub, invoice)
            _send_trial_converted_notice(sub)
            logger.info("Trial convertido a activo: tenant=%s", sub.tenant_id)
        else:
            # Sin pago → bajar a Free y notificar
            register_payment_failure(sub, invoice, error_msg=result.get("error", ""))
            _send_trial_expired_notice(sub)
            logger.info("Trial vencido sin pago: tenant=%s → downgrade a Free", sub.tenant_id)

        converted += 1

    logger.info("expire_trials: %d trials procesados", converted)
    return {"converted": converted}


# ─────────────────────────────────────────────────────────────
# HELPERS DE EMAIL
# ─────────────────────────────────────────────────────────────
def _get_owner_email(sub) -> str | None:
    """Obtiene el email del dueño del tenant."""
    from core.models import User
    owner = User.objects.filter(
        tenant=sub.tenant, role="owner", is_active=True
    ).values("email").first()
    return owner["email"] if owner and owner["email"] else None


APP_URL = "https://app.pulstock.cl"
SETTINGS_URL = f"{APP_URL}/dashboard/settings?tab=suscripcion"
BRAND = "Pulstock"
SUPPORT_EMAIL = "soporte@pulstock.cl"


def _send_email_safe(to: str, subject: str, body: str, html_message: str | None = None):
    """Envía email con logging de errores. No silencia fallos."""
    if not to:
        logger.warning("_send_email_safe: no recipient, skipping: %s", subject)
        return
    try:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", f"{BRAND} <noreply@pulstock.cl>")
        send_mail(subject, body, from_email, [to],
                  fail_silently=False, html_message=html_message)
        logger.info("Email enviado a %s: %s", to, subject)
    except Exception as e:
        logger.error("Email FALLÓ a %s: %s — %s", to, subject, e)
        raise


def _billing_html(title: str, color: str, body_html: str, cta_text: str | None = None, cta_url: str | None = None) -> str:
    """Wrap billing email content in branded HTML template."""
    cta = ""
    if cta_text and cta_url:
        cta = f"""
        <div style="text-align:center;margin:24px 0 8px;">
            <a href="{cta_url}" style="display:inline-block;padding:12px 28px;background:#4F46E5;color:#fff;
               font-size:13px;font-weight:700;text-decoration:none;border-radius:8px;">{cta_text}</a>
        </div>"""

    return f"""
    <div style="font-family:'DM Sans',Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;color:#18181B;">
        <div style="background:{color};padding:20px 24px;border-radius:12px 12px 0 0;">
            <h1 style="margin:0;color:#fff;font-size:18px;font-weight:800;">{title}</h1>
        </div>
        <div style="background:#fff;border:1px solid #E4E4E7;border-top:none;padding:24px;border-radius:0 0 12px 12px;">
            {body_html}
            {cta}
            <p style="margin:20px 0 0;font-size:11px;color:#A1A1AA;text-align:center;">
                {BRAND} · <a href="{APP_URL}" style="color:#4F46E5;text-decoration:none;">{APP_URL}</a>
            </p>
        </div>
    </div>"""


def _send_trial_reminder(sub, days_left: int):
    email = _get_owner_email(sub)
    d = "día" if days_left == 1 else "días"
    subject = f"Tu prueba vence en {days_left} {d} — {BRAND}"
    plain = f"Tu período de prueba de {BRAND} vence en {days_left} {d}. Plan: {sub.plan.name}. Gestiona tu suscripción en {SETTINGS_URL}"
    html = _billing_html(f"⏰ Tu prueba vence en {days_left} {d}", "#D97706", f"""
        <p style="font-size:14px;margin:0 0 16px;">Tu período de prueba vence pronto.</p>
        <div style="background:#F9FAFB;border:1px solid #E4E4E7;border-radius:10px;padding:16px;margin-bottom:16px;">
            <div style="font-size:12px;color:#71717A;">Plan actual</div>
            <div style="font-size:20px;font-weight:800;margin:4px 0;">{sub.plan.name}</div>
            <div style="font-size:13px;color:#52525B;">${sub.plan.price_clp:,} CLP/mes</div>
        </div>
        <p style="font-size:13px;color:#52525B;margin:0;">Si no agregas un método de pago, tu cuenta pasará al plan Gratuito.</p>
    """, "Gestionar suscripción", SETTINGS_URL)
    _send_email_safe(email, subject, plain, html)


def _send_renewal_reminder(sub, days_left: int):
    email = _get_owner_email(sub)
    d = "día" if days_left == 1 else "días"
    fecha = sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else 'pronto'
    subject = f"Tu suscripción se renueva en {days_left} {d} — {BRAND}"
    plain = f"Tu suscripción {BRAND} se renueva en {days_left} {d}. Plan: {sub.plan.name}, ${sub.plan.price_clp:,} CLP. Fecha: {fecha}"
    html = _billing_html(f"📅 Renovación en {days_left} {d}", "#4F46E5", f"""
        <p style="font-size:14px;margin:0 0 16px;">Tu suscripción se renovará automáticamente.</p>
        <div style="background:#F9FAFB;border:1px solid #E4E4E7;border-radius:10px;padding:16px;margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:12px;color:#71717A;">Plan</span>
                <span style="font-size:13px;font-weight:700;">{sub.plan.name}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:12px;color:#71717A;">Monto</span>
                <span style="font-size:13px;font-weight:700;">${sub.plan.price_clp:,} CLP</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
                <span style="font-size:12px;color:#71717A;">Fecha de cobro</span>
                <span style="font-size:13px;font-weight:700;">{fecha}</span>
            </div>
        </div>
    """, "Ver suscripción", SETTINGS_URL)
    _send_email_safe(email, subject, plain, html)


def _send_payment_failed_notice(sub):
    email = _get_owner_email(sub)
    subject = f"⚠️ Problema con tu pago — {BRAND}"
    plain = f"No pudimos cobrar tu suscripción {BRAND}. Plan: {sub.plan.name}, ${sub.plan.price_clp:,} CLP. Intento {sub.payment_retry_count}/3. Actualiza tu pago en {SETTINGS_URL}"
    html = _billing_html("⚠️ No pudimos procesar tu pago", "#DC2626", f"""
        <p style="font-size:14px;margin:0 0 16px;">Hubo un problema con el cobro de tu suscripción.</p>
        <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:10px;padding:16px;margin-bottom:16px;">
            <div style="font-size:13px;font-weight:700;color:#DC2626;margin-bottom:4px;">Plan: {sub.plan.name} — ${sub.plan.price_clp:,} CLP</div>
            <div style="font-size:12px;color:#52525B;">Intento {sub.payment_retry_count} de 3 · Tu acceso se mantiene por 3 días más.</div>
        </div>
        <p style="font-size:13px;color:#52525B;margin:0;">Actualiza tu método de pago para evitar la suspensión.</p>
    """, "Actualizar método de pago", SETTINGS_URL)
    _send_email_safe(email, subject, plain, html)


def _send_suspension_notice(sub):
    email = _get_owner_email(sub)
    subject = f"🔒 Cuenta suspendida — {BRAND}"
    plain = f"Tu cuenta {BRAND} ha sido suspendida por falta de pago. Tus datos se conservan 30 días. Reactiva en {SETTINGS_URL}. Ayuda: {SUPPORT_EMAIL}"
    html = _billing_html("🔒 Tu cuenta ha sido suspendida", "#18181B", f"""
        <p style="font-size:14px;margin:0 0 16px;">No pudimos procesar tu pago después de 3 intentos.</p>
        <div style="background:#F9FAFB;border:1px solid #E4E4E7;border-radius:10px;padding:16px;margin-bottom:16px;">
            <p style="font-size:13px;color:#52525B;margin:0 0 8px;">Tus datos están seguros y se conservarán por <strong>30 días</strong>.</p>
            <p style="font-size:13px;color:#52525B;margin:0;">Reactiva tu cuenta actualizando tu método de pago.</p>
        </div>
        <p style="font-size:12px;color:#71717A;margin:0;">¿Necesitas ayuda? <a href="mailto:{SUPPORT_EMAIL}" style="color:#4F46E5;">{SUPPORT_EMAIL}</a></p>
    """, "Reactivar cuenta", SETTINGS_URL)
    _send_email_safe(email, subject, plain, html)


def _send_payment_recovered_notice(sub):
    email = _get_owner_email(sub)
    fecha = sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else '—'
    subject = f"✅ Pago procesado — {BRAND}"
    plain = f"Tu pago de {BRAND} fue procesado. Plan: {sub.plan.name}. Próximo cobro: {fecha}."
    html = _billing_html("✅ Pago procesado exitosamente", "#16A34A", f"""
        <p style="font-size:14px;margin:0 0 16px;">Tu suscripción está activa.</p>
        <div style="background:#ECFDF5;border:1px solid #A7F3D0;border-radius:10px;padding:16px;margin-bottom:16px;">
            <div style="font-size:13px;font-weight:700;color:#16A34A;">Plan: {sub.plan.name}</div>
            <div style="font-size:12px;color:#52525B;margin-top:4px;">Próximo cobro: {fecha}</div>
        </div>
        <p style="font-size:13px;color:#52525B;margin:0;">Gracias por confiar en {BRAND}.</p>
    """)
    _send_email_safe(email, subject, plain, html)


def _send_trial_converted_notice(sub):
    email = _get_owner_email(sub)
    fecha = sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else '—'
    subject = f"✅ Suscripción activada — {BRAND}"
    plain = f"Tu prueba terminó y tu suscripción {BRAND} está activa. Plan: {sub.plan.name}, ${sub.plan.price_clp:,} CLP/mes. Próximo cobro: {fecha}."
    html = _billing_html("✅ Suscripción activada", "#16A34A", f"""
        <p style="font-size:14px;margin:0 0 16px;">Tu período de prueba terminó y tu plan está activo.</p>
        <div style="background:#ECFDF5;border:1px solid #A7F3D0;border-radius:10px;padding:16px;margin-bottom:16px;">
            <div style="font-size:13px;font-weight:700;color:#16A34A;">{sub.plan.name} — ${sub.plan.price_clp:,} CLP/mes</div>
            <div style="font-size:12px;color:#52525B;margin-top:4px;">Próximo cobro: {fecha}</div>
        </div>
    """)
    _send_email_safe(email, subject, plain, html)


def _send_trial_expired_notice(sub):
    email = _get_owner_email(sub)
    subject = f"Tu prueba terminó — {BRAND}"
    plain = f"Tu prueba de {BRAND} terminó. Tu cuenta está en plan Gratuito. Para volver a {sub.plan.name}: {SETTINGS_URL}"
    html = _billing_html("Tu período de prueba terminó", "#D97706", f"""
        <p style="font-size:14px;margin:0 0 16px;">No pudimos procesar el pago. Tu cuenta está ahora en el plan Gratuito.</p>
        <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;padding:16px;margin-bottom:16px;">
            <div style="font-size:13px;font-weight:700;color:#D97706;margin-bottom:8px;">Plan Gratuito:</div>
            <ul style="margin:0;padding:0 0 0 16px;font-size:12px;color:#52525B;">
                <li>Hasta 100 productos</li>
                <li>1 local, 1 bodega</li>
                <li>1 usuario</li>
            </ul>
        </div>
        <p style="font-size:13px;color:#52525B;margin:0;">Para volver al plan <strong>{sub.plan.name}</strong> (${sub.plan.price_clp:,} CLP/mes):</p>
    """, f"Volver a {sub.plan.name}", SETTINGS_URL)
    _send_email_safe(email, subject, plain, html)