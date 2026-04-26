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

    Thread-safe: cada sub se lockea con select_for_update(skip_locked=True)
    para evitar double-charge si el job corre duplicado (dos beats, race).
    Si otro proceso ya tiene el lock, lo saltamos en esta iteración.
    """
    from django.conf import settings as dj_settings
    from django.db import transaction as db_transaction
    from .models import Subscription, Plan
    from .services import create_invoice, register_payment_failure
    from .gateway import charge_subscription

    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    now = timezone.now()

    # Listar IDs primero (sin lock) para no hacer lock de toda la tabla
    due_ids = list(
        Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            current_period_end__lte=now,
        ).exclude(tenant__slug__in=lifetime_slugs).values_list("pk", flat=True)
    )

    processed = 0
    skipped_locked = 0
    for sub_id in due_ids:
        try:
            # Atomic + lock por subscription individual
            with db_transaction.atomic():
                try:
                    sub = (
                        Subscription.objects
                        .select_for_update(skip_locked=True)
                        .select_related("tenant", "plan")
                        .get(pk=sub_id)
                    )
                except Subscription.DoesNotExist:
                    # Fue cancelada entre el listado y ahora
                    continue

                # Re-chequear condición bajo el lock (puede haberse renovado
                # por otro proceso o haber cambiado de estado)
                if sub.status != Subscription.Status.ACTIVE:
                    continue
                if sub.current_period_end > now:
                    continue

                invoice = create_invoice(sub)
                result = charge_subscription(sub, invoice)

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
            logger.error("Error procesando renovación sub=%s: %s", sub_id, exc)

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

    # Listar IDs primero (sin lock) para no tomar locks masivos. Después
    # tomamos el lock por sub individual dentro del loop — mismo patrón que
    # process_renewals — para evitar double-charge si Celery beat corre
    # duplicado por cualquier razón.
    from django.db import transaction as db_transaction

    due_ids = list(
        Subscription.objects.filter(
            status=Subscription.Status.PAST_DUE,
            next_retry_at__lte=now,
            next_retry_at__isnull=False,
        ).exclude(tenant__slug__in=lifetime_slugs).values_list("pk", flat=True)
    )

    for sub_id in due_ids:
        try:
            with db_transaction.atomic():
                try:
                    sub = (
                        Subscription.objects
                        .select_for_update(skip_locked=True)
                        .select_related("tenant", "plan")
                        .get(pk=sub_id)
                    )
                except Subscription.DoesNotExist:
                    continue

                # Re-check bajo el lock: el estado pudo cambiar entre la
                # selección de IDs y ahora (ej. pago recibido, suspendida, etc.)
                if sub.status != Subscription.Status.PAST_DUE:
                    continue
                if not sub.next_retry_at or sub.next_retry_at > now:
                    continue

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
            logger.error("Error en reintento sub=%s: %s", sub_id, exc)

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
    Corre diariamente. Procesa trials vencidos:

    - Si la suscripción TIENE tarjeta registrada (`flow_customer_id` +
      `card_last4`), intenta cobrar el primer período. Si OK → ACTIVE.
      Si falla → PAST_DUE (entra al ciclo de retries).

    - Si la suscripción NO tiene tarjeta → `status=CANCELLED`. Pulstock
      no tiene plan Free, así que sin método de pago el cliente pierde
      acceso. El email "trial_expired" lo invita a agregar tarjeta para
      reactivar (los datos se conservan 30 días).

    El status `CANCELLED` es preferible a `PAST_DUE` para este caso
    porque PAST_DUE implica un cobro fallido pendiente de retry, lo cual
    no aplica acá: el cliente nunca puso tarjeta para fallar el cobro.
    """
    from django.conf import settings as dj_settings
    from .models import Subscription, Plan
    from .services import create_invoice, activate_period, register_payment_failure
    from .gateway import charge_subscription

    lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
    now = timezone.now()

    # Mismo patrón que process_renewals / retry_failed_payments: listar IDs,
    # después lock por sub individual para evitar double-charge si Celery
    # beat por accidente corre duplicado.
    from django.db import transaction as db_transaction

    due_ids = list(
        Subscription.objects.filter(
            status=Subscription.Status.TRIALING,
            trial_ends_at__lte=now,
        ).exclude(tenant__slug__in=lifetime_slugs).values_list("pk", flat=True)
    )

    converted = 0
    for sub_id in due_ids:
        try:
            with db_transaction.atomic():
                try:
                    sub = (
                        Subscription.objects
                        .select_for_update(skip_locked=True)
                        .select_related("tenant", "plan")
                        .get(pk=sub_id)
                    )
                except Subscription.DoesNotExist:
                    continue

                # Re-check bajo lock: el trial pudo haber sido convertido
                # manualmente o haber cambiado de estado entre la selección y
                # el lock.
                if sub.status != Subscription.Status.TRIALING:
                    continue
                if not sub.trial_ends_at or sub.trial_ends_at > now:
                    continue

                # ── Sin tarjeta: cancelar suscripción, no intentar cobrar ──
                # Si no hay flow_customer_id ni card_last4, no tiene sentido
                # crear un Invoice ni llamar al gateway: el cliente nunca
                # ingresó método de pago. Marcamos cancelled y notificamos.
                if not sub.flow_customer_id or not sub.card_last4:
                    sub.status = Subscription.Status.CANCELLED
                    sub.cancelled_at = now
                    sub.save(update_fields=["status", "cancelled_at"])
                    _send_trial_expired_notice(sub)
                    logger.info(
                        "Trial vencido sin tarjeta: tenant=%s → cancelled",
                        sub.tenant_id,
                    )
                    converted += 1
                    continue

                # ── Con tarjeta: intentar cobrar el primer período ──
                invoice = create_invoice(sub)
                result  = charge_subscription(sub, invoice)

                if result["success"]:
                    activate_period(sub, invoice)
                    _send_trial_converted_notice(sub)
                    logger.info("Trial convertido a activo: tenant=%s", sub.tenant_id)
                else:
                    # Tarjeta registrada pero el cobro falló → entra al ciclo
                    # de retries (PAST_DUE) en lugar de cancelar de inmediato.
                    register_payment_failure(sub, invoice, error_msg=result.get("error", ""))
                    _send_payment_failed_notice(sub)
                    logger.info(
                        "Trial con tarjeta cobro fallido: tenant=%s → past_due",
                        sub.tenant_id,
                    )

                converted += 1
        except Exception as exc:
            logger.error("Error procesando trial sub=%s: %s", sub_id, exc)

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


# URLs y branding — estos son los fallbacks en caso que algún renderer los necesite.
# Los renderers de email (email_renderers.py) tienen sus propias constantes.
APP_URL = "https://app.pulstock.cl"
SETTINGS_URL = f"{APP_URL}/dashboard/settings?tab=plan"
BRAND = "Pulstock"
SUPPORT_EMAIL = "pulstock.admin@gmail.com"


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


# ─────────────────────────────────────────────────────────────
# EMAIL RENDERING — todas las plantillas viven en
# apps/api/billing/templates/emails/*.html y se renderean vía
# apps/api/billing/email_renderers.py (sistema unificado cross-client).
#
# Las firmas de estas funciones se mantienen tal cual las llaman otros
# módulos (billing/services.py, billing/views.py, etc.) para no romper
# call sites. El HTML se arma adentro del renderer correspondiente.
# ─────────────────────────────────────────────────────────────
def _send_welcome_email(user, tenant, plan):
    """Email de bienvenida post-pago / alta de cuenta."""
    if not user or not user.email:
        logger.warning("welcome_email: user sin email, skipping (user_id=%s)", getattr(user, "pk", None))
        return

    from billing.email_renderers import render_welcome
    subject, plain, html = render_welcome(user, tenant, plan)
    _send_email_safe(user.email, subject, plain, html)


def _send_trial_reminder(sub, days_left: int):
    email = _get_owner_email(sub)
    from billing.email_renderers import render_trial_reminder
    subject, plain, html = render_trial_reminder(sub, days_left)
    _send_email_safe(email, subject, plain, html)


def _send_renewal_reminder(sub, days_left: int):
    email = _get_owner_email(sub)
    from billing.email_renderers import render_renewal_reminder
    subject, plain, html = render_renewal_reminder(
        sub, days_left,
        payment_method=_sub_payment_method(sub),
    )
    _send_email_safe(email, subject, plain, html)


def _send_payment_failed_notice(sub):
    email = _get_owner_email(sub)
    invoice_number = _latest_invoice_number(sub)
    # El último Invoice (en estado FAILED o PENDING) debería tener el motivo
    # real del rechazo guardado por el webhook. Si está vacío, pasamos None
    # y el renderer usa un mensaje genérico ("el banco no autorizó...").
    failure_reason = _latest_invoice_failure_message(sub)
    from billing.email_renderers import render_payment_failed
    subject, plain, html = render_payment_failed(
        sub, invoice_number,
        failure_reason=failure_reason,
        payment_method=_sub_payment_method(sub),
    )
    _send_email_safe(email, subject, plain, html)


def _send_suspension_notice(sub):
    email = _get_owner_email(sub)
    from billing.email_renderers import render_suspension
    subject, plain, html = render_suspension(sub)
    _send_email_safe(email, subject, plain, html)


def _send_payment_recovered_notice(sub):
    email = _get_owner_email(sub)
    # Buscamos el último Invoice pagado para usar los datos REALES de esa
    # transacción (card_last4 + card_brand + paid_at). Si no existe, caemos
    # a los valores del Subscription (mirror del último pago OK).
    inv = _latest_paid_invoice(sub)
    invoice_number = f"INV-{inv.pk:05d}" if inv else _latest_invoice_number(sub)
    payment_method = _invoice_payment_method(inv) if inv else _sub_payment_method(sub)
    charged_at = (inv.paid_at if inv else None)
    amount = (inv.amount_clp if inv else None)

    from billing.email_renderers import render_payment_recovered
    subject, plain, html = render_payment_recovered(
        sub, invoice_number,
        amount=amount,
        payment_method=payment_method,
        charged_at=charged_at,
    )
    _send_email_safe(email, subject, plain, html)


def _send_trial_converted_notice(sub):
    email = _get_owner_email(sub)
    # Al convertir un trial, el primer cobro ya se hizo → leer la tarjeta
    # real del último Invoice pagado o, fallback, del Subscription.
    inv = _latest_paid_invoice(sub)
    payment_method = _invoice_payment_method(inv) if inv else _sub_payment_method(sub)
    from billing.email_renderers import render_trial_converted
    subject, plain, html = render_trial_converted(
        sub, payment_method=payment_method,
    )
    _send_email_safe(email, subject, plain, html)


def _send_trial_expired_notice(sub):
    email = _get_owner_email(sub)
    products_count = 0
    try:
        from catalog.models import Product
        products_count = Product.objects.filter(
            tenant=sub.tenant, is_active=True
        ).count()
    except Exception:
        pass

    from billing.email_renderers import render_trial_expired
    subject, plain, html = render_trial_expired(sub, products_count=products_count)
    _send_email_safe(email, subject, plain, html)


def _latest_invoice_number(sub) -> str:
    """Devuelve un número de factura para mostrar en el email.

    Invoice no tiene campo `number` explícito, usamos el ID formateado.
    Si no hay invoice, usamos el ID de la suscripción.
    """
    try:
        from billing.models import Invoice
        inv_id = (
            Invoice.objects.filter(subscription=sub)
            .order_by("-created_at")
            .values_list("id", flat=True)
            .first()
        )
        if inv_id:
            return f"INV-{inv_id:05d}"
    except Exception:
        pass
    return f"INV-{getattr(sub, 'pk', 0):05d}"


def _sub_payment_method(sub) -> str | None:
    """Construye el string 'Visa ···· 4829' desde Subscription.card_brand + card_last4.

    Si la suscripción no tiene tarjeta registrada aún (campos vacíos),
    devuelve None para que el renderer use su fallback genérico.

    Subscription guarda un mirror del último pago OK (se syncea en el
    webhook), así que esto funciona tanto para renewal como para
    payment_failed (el sub sigue teniendo la tarjeta aunque el último
    cobro haya fallado).
    """
    brand = (getattr(sub, "card_brand", "") or "").strip()
    last4 = (getattr(sub, "card_last4", "") or "").strip()
    if not last4:
        return None
    if brand:
        return f"{brand} ···· {last4}"
    return f"Tarjeta ···· {last4}"


def _invoice_payment_method(invoice) -> str | None:
    """Construye el payment_method desde los campos del Invoice.

    Preferido sobre _sub_payment_method cuando queremos mostrar el método
    exacto con el que se cobró ESE invoice (ej. en payment_recovered y
    trial_converted). El Subscription.card_* puede haber cambiado después.
    """
    if not invoice:
        return None
    brand = (getattr(invoice, "card_brand", "") or "").strip()
    last4 = (getattr(invoice, "card_last4", "") or "").strip()
    if not last4:
        return None
    if brand:
        return f"{brand} ···· {last4}"
    return f"Tarjeta ···· {last4}"


def _latest_paid_invoice(sub):
    """Último Invoice en estado PAID (o None si nunca se pagó).

    Usado para mostrar datos reales en los emails payment_recovered y
    trial_converted (amount, card, paid_at reales).

    Nota: ordenamos por `-created_at, -pk` para tener orden determinístico
    cuando múltiples invoices se crean en el mismo segundo (caso común en
    tests y posible en producción con webhooks rápidos).
    """
    try:
        from billing.models import Invoice
        return (
            Invoice.objects.filter(subscription=sub, status=Invoice.Status.PAID)
            .order_by("-created_at", "-pk")
            .first()
        )
    except Exception:
        return None


def _latest_invoice_failure_message(sub) -> str | None:
    """Mensaje de error del último Invoice fallido o pendiente de retry.

    Viene de `paymentData.lastError.message` de Flow (ej. 'Tarjeta vencida',
    'Fondos insuficientes', 'CVV incorrecto') y fue guardado por el webhook
    como Invoice.failure_message. Si no existe, None → el renderer usa un
    mensaje genérico.
    """
    try:
        from billing.models import Invoice
        inv = (
            Invoice.objects.filter(
                subscription=sub,
                status__in=[Invoice.Status.FAILED, Invoice.Status.PENDING],
            )
            .exclude(failure_message="")
            .order_by("-created_at", "-pk")
            .first()
        )
        if inv and inv.failure_message:
            return inv.failure_message
    except Exception:
        pass
    return None


