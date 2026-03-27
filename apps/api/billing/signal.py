"""
billing/signals.py
==================
Señales para automatizar el ciclo de vida de suscripciones.

- post_save en Tenant → crea suscripción automáticamente.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="core.Tenant")
def create_tenant_subscription(sender, instance, created, **kwargs):
    """
    Cuando se crea un nuevo Tenant, le asigna automáticamente
    una suscripción en plan Pro con 7 días de trial.
    """
    if not created:
        return
    if getattr(instance, "_skip_subscription", False):
        return

    # Evitar import circular
    from .models import Subscription, Plan
    from .services import create_subscription

    if not Subscription.objects.filter(tenant=instance).exists():
        try:
            create_subscription(instance, plan_key=Plan.PlanKey.PRO)
        except Plan.DoesNotExist:
            # Los planes aún no están en la DB (primera migración)
            pass