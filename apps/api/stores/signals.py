from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from core.models import Tenant, Warehouse
from .models import Store


@receiver(post_save, sender=Tenant)
def create_default_store_and_warehouse(sender, instance, created, **kwargs):
    """
    Al crear un Tenant:
    1) Crea un Store "Local Principal" (si no existe)
    2) Crea una Warehouse "Bodega Principal" para ese store (si no existe)
    3) (Opcional) setea tenant.default_warehouse si está vacío

    Se salta si el caller setea _skip_default_store=True en la instancia
    (e.g. RegisterView que crea stores con nombres personalizados).
    """
    if not created:
        return

    # RegisterView sets this flag before creating the tenant
    if getattr(instance, "_skip_default_store", False):
        return

    with transaction.atomic():
        store = Store.objects.create(
            tenant=instance,
            name="Local Principal",
            code="LOCAL-1",
            is_active=True,
        )

        wh = Warehouse.objects.create(
            tenant=instance,
            store=store,
            name="Bodega Principal",
            is_active=True,
        )

        if instance.default_warehouse_id is None:
            Tenant.objects.filter(pk=instance.pk).update(default_warehouse=wh)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_active_store(sender, instance, created, **kwargs):
    """
    Si el usuario tiene tenant y NO tiene active_store, asigna el primer store activo.
    Esto evita errores en el primer ingreso.
    """
    if not instance.tenant_id:
        return

    if instance.active_store_id:
        return

    store = (
        Store.objects
        .filter(tenant_id=instance.tenant_id, is_active=True)
        .order_by("id")
        .first()
    )
    if store:
        # ✅ update directo para evitar loops y señales innecesarias
        type(instance).objects.filter(pk=instance.pk).update(active_store=store)
