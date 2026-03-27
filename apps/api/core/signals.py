from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Tenant, Warehouse

@receiver(post_save, sender=Tenant)
def ensure_default_warehouse(sender, instance: Tenant, created, **kwargs):
    if not instance.default_warehouse_id:
        wh = Warehouse.objects.filter(tenant=instance).order_by("id").first()
        if wh:
            Tenant.objects.filter(id=instance.id, default_warehouse__isnull=True).update(default_warehouse=wh)