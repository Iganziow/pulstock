"""
inventory/tasks.py
==================
Celery tasks for inventory alerts.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F, Q

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:
    def shared_task(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper if args and callable(args[0]) is False else wrapper


@shared_task(name="inventory.tasks.send_low_stock_alerts", bind=True,
             max_retries=3, autoretry_for=(Exception,),
             retry_backoff=True, retry_backoff_max=600,
             soft_time_limit=300, time_limit=360)
def send_low_stock_alerts(self):
    """
    Runs daily at 7:30am. Sends email to tenant owners when products are
    below their min_stock threshold.
    """
    from core.models import Tenant, User, AlertPreference
    from inventory.models import StockItem

    sent = 0
    for tenant in Tenant.objects.filter(is_active=True):
        # Check owner preferences
        owner = User.objects.filter(
            tenant=tenant, role="owner", is_active=True
        ).first()
        if not owner or not owner.email:
            continue

        # Check if stock_bajo alert is enabled
        try:
            prefs = AlertPreference.objects.get(user=owner)
            if not prefs.stock_bajo:
                continue
        except AlertPreference.DoesNotExist:
            pass  # No prefs = defaults (stock_bajo=True)

        # Query low stock items: on_hand < product.min_stock where min_stock > 0
        low_items = list(
            StockItem.objects
            .filter(
                tenant=tenant,
                product__min_stock__gt=0,
                product__is_active=True,
            )
            .filter(on_hand__lt=F("product__min_stock"))
            .select_related("product", "warehouse")
            .order_by("on_hand")[:20]
        )

        if not low_items:
            continue

        # Critical: on_hand = 0
        critical = [i for i in low_items if i.on_hand <= 0]
        low = [i for i in low_items if i.on_hand > 0]

        from billing.email_renderers import render_low_stock
        subject, plain, html = render_low_stock(
            tenant=tenant,
            critical_items=critical,
            low_items=low,
        )

        try:
            send_mail(
                subject=subject,
                message=plain,
                html_message=html,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "Pulstock <noreply@pulstock.cl>"),
                recipient_list=[owner.email],
                fail_silently=False,
            )
            sent += 1
            logger.info("Low stock alert sent to %s (tenant %s, %d items)",
                        owner.email, tenant.id, len(low_items))
        except Exception as e:
            logger.error("Failed to send low stock alert to %s: %s", owner.email, e)
            raise

    logger.info("send_low_stock_alerts: %d emails sent", sent)
    return {"sent": sent}
