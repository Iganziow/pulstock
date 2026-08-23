"""
reports/tasks.py
================
Celery tasks for automated report delivery.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:
    def shared_task(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper if args and callable(args[0]) is False else wrapper


@shared_task(name="reports.tasks.send_weekly_abc_report", bind=True,
             max_retries=3, autoretry_for=(Exception,),
             retry_backoff=True, retry_backoff_max=600,
             soft_time_limit=300, time_limit=360)
def send_weekly_abc_report(self):
    """
    Runs every Monday 8am. Sends ABC analysis email (HTML) to all active tenant owners.
    """
    from core.models import Tenant, User
    from stores.models import Store
    from reports.services import get_abc_analysis

    now = timezone.now()
    date_to = now.date()
    date_from = date_to - timedelta(days=90)

    sent = 0
    for tenant in Tenant.objects.filter(is_active=True):
        # Duenos Y encargados que lo tengan encendido, no solo el primer
        # dueno. Misma regla que la alerta de quiebre (core.alert_recipients).
        from core.alert_recipients import destinatarios
        usuarios = destinatarios(tenant, "reporte_abc")
        if not usuarios:
            continue

        # Get the first active store for the tenant
        store = Store.objects.filter(tenant=tenant, is_active=True).first()
        if not store:
            continue

        try:
            data = get_abc_analysis(
                t_id=tenant.id, s_id=store.id,
                criterion="revenue",
                date_from=date_from, date_to=date_to,
            )
        except Exception as e:
            logger.warning("ABC analysis failed for tenant %s: %s", tenant.id, e)
            continue

        # get_abc_analysis entrega la lista en "results" (no "items").
        items = data.get("results", [])
        if not items:
            continue

        # Build summary
        a_items = [i for i in items if i["abc_class"] == "A"]
        b_items = [i for i in items if i["abc_class"] == "B"]
        c_items = [i for i in items if i["abc_class"] == "C"]

        total_revenue = sum(float(i["revenue"]) for i in items)
        total_profit = sum(float(i["profit"]) for i in items)

        from billing.email_renderers import render_abc_weekly
        subject, plain, html = render_abc_weekly(
            tenant=tenant,
            date_from=date_from,
            date_to=date_to,
            items_a=a_items,
            items_b=b_items,
            items_c=c_items,
            total_revenue=total_revenue,
            total_profit=total_profit,
        )

        # Un correo por persona: cada quien puede darse de baja sin afectar
        # al resto, y una direccion rechazada no tumba los demas envios.
        for u in usuarios:
            try:
                send_mail(
                    subject=subject,
                    message=plain,
                    html_message=html,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL",
                                       "Pulstock <noreply@pulstock.cl>"),
                    recipient_list=[u.email],
                    fail_silently=False,
                )
                sent += 1
                logger.info("ABC report sent to %s (tenant %s)", u.email, tenant.id)
            except Exception as exc:
                logger.error("ABC report FAILED to %s (tenant %s): %s",
                             u.email, tenant.id, exc)

    logger.info("send_weekly_abc_report: %d emails sent", sent)
    return {"sent": sent}

