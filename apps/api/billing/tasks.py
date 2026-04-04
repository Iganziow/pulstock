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
    from .models import Subscription, Plan
    from .services import create_invoice, register_payment_failure
    from .gateway import charge_subscription

    now = timezone.now()
    due = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        current_period_end__lte=now,
    ).select_related("tenant", "plan")

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
    from .models import Subscription
    from .services import GRACE_PERIOD_DAYS, RETRY_SCHEDULE

    now = timezone.now()
    suspended_count = 0

    past_due = Subscription.objects.filter(
        status=Subscription.Status.PAST_DUE,
    ).select_related("tenant", "plan")

    for sub in past_due:
        # Calcular cuándo se debe suspender
        # Referencia: cuándo terminó el período legítimo
        reference = sub.current_period_end or sub.suspended_at or sub.updated_at
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
    from .models import Subscription, Invoice
    from .services import create_invoice, register_payment_failure, activate_period
    from .gateway import charge_subscription

    now = timezone.now()
    retried = 0

    to_retry = Subscription.objects.filter(
        status=Subscription.Status.PAST_DUE,
        next_retry_at__lte=now,
        next_retry_at__isnull=False,
    ).select_related("tenant", "plan")

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
    from .models import Subscription, Plan
    from .services import change_plan, create_invoice, activate_period, register_payment_failure
    from .gateway import charge_subscription

    now = timezone.now()
    expired = Subscription.objects.filter(
        status=Subscription.Status.TRIALING,
        trial_ends_at__lte=now,
    ).select_related("tenant", "plan")

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


def _send_email_safe(to: str, subject: str, body: str, html_message: str | None = None):
    """Envía email con logging de errores. No silencia fallos."""
    if not to:
        logger.warning("_send_email_safe: no recipient, skipping: %s", subject)
        return
    try:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@inventario.pro")
        send_mail(subject, body, from_email, [to],
                  fail_silently=False, html_message=html_message)
        logger.info("Email enviado a %s: %s", to, subject)
    except Exception as e:
        logger.error("Email FALLÓ a %s: %s — %s", to, subject, e)
        # Re-raise para que Celery pueda reintentar la task
        raise


def _send_trial_reminder(sub, days_left: int):
    email = _get_owner_email(sub)
    subject = f"Tu prueba gratuita vence en {days_left} día{'s' if days_left != 1 else ''}"
    body = f"""Hola,

Tu período de prueba de inventario.pro vence en {days_left} día{'s' if days_left != 1 else ''}.

Plan actual: {sub.plan.name}
Precio mensual: ${sub.plan.price_clp:,} CLP

Para mantener el acceso, agrega un método de pago en:
https://app.inventario.pro/dashboard/settings?tab=suscripcion

Si no agregas un método de pago, tu cuenta pasará al plan Gratuito
(máximo 100 productos, 1 local, 1 usuario).

Equipo inventario.pro
"""
    _send_email_safe(email, subject, body)


def _send_renewal_reminder(sub, days_left: int):
    email = _get_owner_email(sub)
    subject = f"Tu suscripción se renueva en {days_left} día{'s' if days_left != 1 else ''}"
    body = f"""Hola,

Tu suscripción de inventario.pro se renovará en {days_left} día{'s' if days_left != 1 else ''}.

Plan: {sub.plan.name}
Monto a cobrar: ${sub.plan.price_clp:,} CLP
Fecha de cobro: {sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else 'pronto'}

Si tienes alguna pregunta sobre tu suscripción:
https://app.inventario.pro/dashboard/settings?tab=suscripcion

Equipo inventario.pro
"""
    _send_email_safe(email, subject, body)


def _send_payment_failed_notice(sub):
    email = _get_owner_email(sub)
    subject = "⚠ Problema con el pago de tu suscripción"
    body = f"""Hola,

No pudimos procesar el pago de tu suscripción inventario.pro.

Plan: {sub.plan.name}
Monto: ${sub.plan.price_clp:,} CLP

Tu acceso se mantiene por {3} días más mientras resuelves el problema.
Intento {sub.payment_retry_count} de 3.

Actualiza tu método de pago aquí:
https://app.inventario.pro/dashboard/settings?tab=suscripcion

Equipo inventario.pro
"""
    _send_email_safe(email, subject, body)


def _send_suspension_notice(sub):
    email = _get_owner_email(sub)
    subject = "🔒 Tu cuenta de inventario.pro ha sido suspendida"
    body = f"""Hola,

Lamentamos informarte que tu cuenta de inventario.pro ha sido suspendida
porque no pudimos procesar el pago de tu suscripción después de 3 intentos.

Tus datos están seguros y se conservarán por 30 días.

Para reactivar tu cuenta:
https://app.inventario.pro/dashboard/settings?tab=suscripcion

Si necesitas ayuda, contáctanos en soporte@inventario.pro

Equipo inventario.pro
"""
    _send_email_safe(email, subject, body)


def _send_payment_recovered_notice(sub):
    email = _get_owner_email(sub)
    subject = "✅ Pago procesado — Suscripción activa"
    body = f"""Hola,

El pago de tu suscripción fue procesado exitosamente.

Plan: {sub.plan.name}
Próximo cobro: {sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else '—'}

Gracias por continuar con inventario.pro.

Equipo inventario.pro
"""
    _send_email_safe(email, subject, body)


def _send_trial_converted_notice(sub):
    email = _get_owner_email(sub)
    subject = "✅ Tu prueba terminó — Suscripción activada"
    body = f"""Hola,

Tu período de prueba terminó y tu suscripción ha sido activada exitosamente.

Plan: {sub.plan.name}
Próximo cobro: {sub.current_period_end.strftime('%d/%m/%Y') if sub.current_period_end else '—'}
Monto: ${sub.plan.price_clp:,} CLP/mes

Equipo inventario.pro
"""
    _send_email_safe(email, subject, body)


def _send_trial_expired_notice(sub):
    email = _get_owner_email(sub)
    subject = "Tu período de prueba terminó — Cuenta en plan Gratuito"
    body = f"""Hola,

Tu período de prueba de inventario.pro terminó y no pudimos procesar el pago.

Tu cuenta ahora está en el plan Gratuito:
- Hasta 100 productos
- 1 local, 1 bodega
- 1 usuario

Para volver al plan {sub.plan.name} (${sub.plan.price_clp:,} CLP/mes):
https://app.inventario.pro/dashboard/settings?tab=suscripcion

Equipo inventario.pro
"""
    _send_email_safe(email, subject, body)