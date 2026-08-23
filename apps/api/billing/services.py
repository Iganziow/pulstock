"""
billing/services.py
===================
Lógica de negocio del sistema de suscripciones.

Separado de las vistas para poder usarse desde:
  - Celery tasks (cobros automáticos)
  - Management commands (seed, fix)
  - Views (API)
  - Signals (onboarding)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import Invoice, PaymentAttempt, Plan, Subscription

logger = logging.getLogger(__name__)


def invalidate_sub_cache(tenant_id: int) -> None:
    """Invalidar cache del middleware de suscripción."""
    cache.delete(f"sub_access:{tenant_id}")

# Días de gracia antes de suspender tras fallo de pago
GRACE_PERIOD_DAYS = 3
# Política de reintentos (días después del fallo)
RETRY_SCHEDULE = [1, 3, 7]   # reintento 1, 3 y 7 días después del primer fallo
# Cuántos días antes del vencimiento avisar
NOTIFY_DAYS_BEFORE = [7, 3, 1]


# ─────────────────────────────────────────────────────────────
# CREACIÓN DE SUSCRIPCIÓN (se llama desde onboarding)
# ─────────────────────────────────────────────────────────────
@transaction.atomic
def create_subscription(tenant, plan_key: str = Plan.PlanKey.PRO) -> Subscription:
    """
    Crea la suscripción inicial de un tenant recién registrado.
    Por defecto arranca en plan PRO con trial de 7 días.
    """
    plan = Plan.objects.get(key=plan_key, is_active=True)
    now  = timezone.now()

    if plan.price_clp == 0:
        sub = Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
        )
    else:
        trial_end = now + timedelta(days=plan.trial_days)
        sub = Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.TRIALING,
            trial_ends_at=trial_end,
            current_period_start=now,
            current_period_end=trial_end,
        )

    logger.info("Suscripción creada: tenant=%s plan=%s status=%s", tenant.id, plan.key, sub.status)
    return sub


# ─────────────────────────────────────────────────────────────
# CAMBIO DE PLAN
# ─────────────────────────────────────────────────────────────
@transaction.atomic
def change_plan(subscription: Subscription, new_plan_key: str) -> Subscription:
    """
    Cambia el plan de una suscripción activa.
    - Upgrade: efectivo inmediato, nuevo período desde hoy.
    - Downgrade: efectivo inmediato, mismas fechas.
    """
    from django.conf import settings as dj_settings
    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    if subscription.tenant and subscription.tenant.slug in lifetime_slugs:
        logger.warning(
            "change_plan: intento de cambiar plan en tenant lifetime=%s (bloqueado)",
            subscription.tenant.slug
        )
        return subscription

    new_plan = Plan.objects.get(key=new_plan_key, is_active=True)
    old_plan = subscription.plan
    now = timezone.now()

    subscription.plan = new_plan

    if new_plan.price_clp == 0:
        # Bajar a Free: cancelar ciclo de cobros
        subscription.status = Subscription.Status.ACTIVE
        subscription.current_period_start = None
        subscription.current_period_end   = None
        subscription.trial_ends_at        = None
    elif subscription.status in (Subscription.Status.TRIALING, Subscription.Status.ACTIVE):
        # Mantener estado, ajustar fechas si es upgrade
        if new_plan.price_clp > old_plan.price_clp:
            subscription.current_period_start = now
            subscription.current_period_end   = now + timedelta(days=30)
            subscription.reset_notification_flags()

    subscription.payment_retry_count = 0
    subscription.next_retry_at = None
    subscription.save()
    invalidate_sub_cache(subscription.tenant_id)

    logger.info(
        "Plan cambiado: tenant=%s %s→%s",
        subscription.tenant_id, old_plan.key, new_plan.key
    )
    return subscription


# ─────────────────────────────────────────────────────────────
# ACTIVAR PERÍODO PAGADO
# ─────────────────────────────────────────────────────────────
@transaction.atomic
def activate_period(subscription: Subscription, invoice: Invoice) -> Subscription:
    """
    Después de un pago exitoso, activa el nuevo período de 30 días.
    """
    now = timezone.now()
    invoice.mark_paid()

    # Nuevo período: si ya había período, lo encadena; si no, desde ahora
    if subscription.current_period_end and subscription.current_period_end > now:
        period_start = subscription.current_period_end
    else:
        period_start = now

    period_end = period_start + timedelta(days=30)

    subscription.status               = Subscription.Status.ACTIVE
    subscription.current_period_start = period_start
    subscription.current_period_end   = period_end
    subscription.payment_retry_count  = 0
    subscription.next_retry_at        = None
    subscription.reset_notification_flags()
    subscription.save()
    invalidate_sub_cache(subscription.tenant_id)

    logger.info(
        "Período activado: tenant=%s período=%s→%s",
        subscription.tenant_id,
        period_start.date(),
        period_end.date()
    )
    return subscription


# ─────────────────────────────────────────────────────────────
# REGISTRAR FALLO DE PAGO
# ─────────────────────────────────────────────────────────────
@transaction.atomic
def register_payment_failure(
    subscription: Subscription,
    invoice: Invoice,
    error_msg: str = "",
    raw: dict = None,
) -> Subscription:
    """
    Registra un fallo, actualiza el contador de reintentos
    y decide si pasar a past_due o suspended.
    """
    now = timezone.now()

    # Registrar intento fallido
    PaymentAttempt.objects.create(
        invoice=invoice,
        result=PaymentAttempt.Result.FAILED,
        error_msg=error_msg,
        raw=raw or {},
    )

    invoice.status = Invoice.Status.FAILED
    invoice.save(update_fields=["status"])

    retry_count = subscription.payment_retry_count + 1
    subscription.payment_retry_count = retry_count

    if retry_count <= len(RETRY_SCHEDULE):
        # Aún hay reintentos disponibles → past_due con gracia
        days_to_retry = RETRY_SCHEDULE[retry_count - 1]
        subscription.next_retry_at = now + timedelta(days=days_to_retry)
        subscription.status = Subscription.Status.PAST_DUE
        # B22: NO marcar notified_past_due aca.
        #
        # El comentario original decia "trigger en task de notificaciones",
        # pero send_payment_reminders busca `notified_past_due=False` para
        # saber a quien avisar. Marcarlo True al fallar el pago hacia que la
        # tarea no lo encontrara nunca: el correo de "no pudimos procesar tu
        # pago" no se enviaba JAMAS.
        #
        # Con B20 desplegado esto pasa de molesto a grave: un cobro fallido ya
        # no activa el periodo, asi que el cliente pierde el servicio y nadie
        # le dice por que. El flag lo pone la tarea DESPUES de enviar.
    else:
        # Agotó reintentos → suspender acceso
        subscription.status       = Subscription.Status.SUSPENDED
        subscription.suspended_at = now
        subscription.next_retry_at = None
        logger.warning(
            "Suscripción SUSPENDIDA: tenant=%s tras %d fallos",
            subscription.tenant_id, retry_count
        )

    subscription.save()
    invalidate_sub_cache(subscription.tenant_id)
    return subscription


# ─────────────────────────────────────────────────────────────
# CANCELAR SUSCRIPCIÓN
# ─────────────────────────────────────────────────────────────
@transaction.atomic
def cancel_subscription(subscription: Subscription, reason: str = "",
                        immediate: bool = False) -> Subscription:
    """Agenda la baja para el fin del período (B21).

    ANTES ponía status=CANCELLED al instante e invalidaba el caché, así que el
    402 llegaba de inmediato — mientras la API le respondía al cliente "tu
    acceso continúa hasta el fin del período actual". El cliente pagaba el mes
    y perdía el servicio el mismo día.

    Ahora la suscripción queda ACTIVE con `cancel_at_period_end=True`: sigue
    funcionando lo que ya pagó, no se renueva, y `expire_cancelled` la pasa a
    CANCELLED cuando corresponde. Es el patrón de Stripe/Paddle, y permite
    arrepentirse (ver `resume_subscription`).

    `immediate=True` queda para soporte/superadmin, que sí necesita cortar ya.
    """
    now = timezone.now()
    if immediate or not subscription.current_period_end or subscription.current_period_end <= now:
        # Sin período vigente que respetar (trial sin pagar, ya vencido, o
        # corte administrativo): la baja es efectiva ahora.
        subscription.status       = Subscription.Status.CANCELLED
        subscription.cancelled_at = now
        subscription.cancel_at_period_end = False
        subscription.save(update_fields=["status", "cancelled_at", "cancel_at_period_end"])
        invalidate_sub_cache(subscription.tenant_id)
        logger.info("Suscripción cancelada YA: tenant=%s reason=%s",
                    subscription.tenant_id, reason)
        return subscription

    subscription.cancel_at_period_end = True
    subscription.cancelled_at = now
    subscription.save(update_fields=["cancel_at_period_end", "cancelled_at"])
    invalidate_sub_cache(subscription.tenant_id)
    logger.info("Baja agendada al fin del período: tenant=%s fin=%s reason=%s",
                subscription.tenant_id, subscription.current_period_end, reason)
    return subscription


def resume_subscription(subscription: Subscription) -> Subscription:
    """Deshace una baja agendada — el cliente se arrepintió.

    Solo tiene sentido mientras el período siga vigente; después de eso la
    suscripción ya está CANCELLED y hay que reactivarla (reactivate_subscription).
    """
    subscription.cancel_at_period_end = False
    subscription.cancelled_at = None
    subscription.save(update_fields=["cancel_at_period_end", "cancelled_at"])
    invalidate_sub_cache(subscription.tenant_id)
    logger.info("Baja revertida: tenant=%s", subscription.tenant_id)
    return subscription


# ─────────────────────────────────────────────────────────────
# REACTIVAR SUSCRIPCIÓN (tras pago manual o admin)
# ─────────────────────────────────────────────────────────────
@transaction.atomic
def reactivate_subscription(subscription: Subscription) -> Subscription:
    now = timezone.now()
    subscription.status               = Subscription.Status.ACTIVE
    subscription.suspended_at         = None
    subscription.cancelled_at         = None
    subscription.payment_retry_count  = 0
    subscription.next_retry_at        = None
    subscription.current_period_start = now
    subscription.current_period_end   = now + timedelta(days=30)
    subscription.reset_notification_flags()
    subscription.save()
    invalidate_sub_cache(subscription.tenant_id)
    logger.info("Suscripción reactivada: tenant=%s", subscription.tenant_id)
    return subscription


# ─────────────────────────────────────────────────────────────
# CREAR INVOICE
# ─────────────────────────────────────────────────────────────
def create_invoice(subscription: Subscription) -> Invoice:
    """Crea o reutiliza una factura PENDING para el período actual (idempotente)."""
    now = timezone.now()
    period_end = (
        subscription.current_period_end.date()
        if subscription.current_period_end
        else (now + timedelta(days=30)).date()
    )
    period_start = (
        subscription.current_period_start.date()
        if subscription.current_period_start
        else now.date()
    )

    # Idempotencia: reusar factura PENDING existente para el mismo período
    existing = Invoice.objects.filter(
        subscription=subscription,
        period_start=period_start,
        period_end=period_end,
        status=Invoice.Status.PENDING,
    ).first()
    if existing:
        logger.info(
            "Invoice existente reutilizada: #%d tenant=%s",
            existing.pk, subscription.tenant_id,
        )
        return existing

    invoice = Invoice.objects.create(
        subscription=subscription,
        amount_clp=subscription.plan.price_clp,
        period_start=period_start,
        period_end=period_end,
        status=Invoice.Status.PENDING,
    )
    logger.info(
        "Invoice creada: #%d tenant=%s monto=$%d",
        invoice.pk, subscription.tenant_id, invoice.amount_clp
    )
    return invoice


# ─────────────────────────────────────────────────────────────
# VERIFICAR LÍMITES DEL PLAN (para enforcement en vistas)
# ─────────────────────────────────────────────────────────────
def check_plan_limit(subscription: Subscription, resource: str, current_count: int) -> dict:
    """
    Verifica si el tenant puede crear más recursos según su plan.
    resource: 'products' | 'stores' | 'users' | 'registers'
    Retorna: { "allowed": bool, "limit": int, "current": int }

    Lifetime tenants (dueño de la app) no tienen límites.
    """
    # Lifetime tenants bypass all limits
    from django.conf import settings as dj_settings
    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    if subscription.tenant and subscription.tenant.slug in lifetime_slugs:
        return {"allowed": True, "limit": -1, "current": current_count}

    plan = subscription.plan
    limits = {
        "products":  plan.max_products,
        "stores":    plan.max_stores,
        "users":     plan.max_users,
        "registers": plan.max_registers,
    }
    limit = limits.get(resource, -1)
    allowed = limit == -1 or current_count < limit
    return {"allowed": allowed, "limit": limit, "current": current_count}


def get_subscription_status_for_api(subscription: Subscription) -> dict:
    """Serializa el estado completo de la suscripción para el frontend."""
    plan = subscription.plan
    now  = timezone.now()

    days_remaining = None
    if subscription.status == Subscription.Status.TRIALING and subscription.trial_ends_at:
        days_remaining = max(0, (subscription.trial_ends_at - now).days)
    elif subscription.current_period_end:
        days_remaining = max(0, (subscription.current_period_end - now).days)

    return {
        "status":           subscription.status,
        "status_label":     subscription.get_status_display(),
        "is_access_allowed": subscription.is_access_allowed,
        # B21: la baja agendada no cambia el estado (sigue ACTIVE hasta que
        # venza lo pagado), asi que sin este campo la UI no tendria como
        # mostrar que la suscripcion ya esta dada de baja.
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "plan": {
            "key":          plan.key,
            "name":         plan.name,
            "price_clp":    plan.price_clp,
            "max_products": plan.max_products,
            "max_stores":    plan.max_stores,
            "max_users":     plan.max_users,
            "max_registers": plan.max_registers,
            "has_forecast":  plan.has_forecast,
            "has_abc":      plan.has_abc,
            "has_reports":  plan.has_reports,
            "has_transfers":plan.has_transfers,
        },
        "trial_ends_at":         subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
        "current_period_end":    subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        "days_remaining":        days_remaining,
        "payment_retry_count":   subscription.payment_retry_count,
        "next_retry_at":         subscription.next_retry_at.isoformat() if subscription.next_retry_at else None,
        "has_card":              bool(subscription.card_last4),
        "card_brand":            subscription.card_brand,
        "card_last4":            subscription.card_last4,
    }