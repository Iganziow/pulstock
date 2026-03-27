from django.db import models
from core.models import Tenant


class Store(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="stores")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, blank=True, default="")  # opcional (ej: LOCAL-1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ NUEVO: bodega por defecto del store (multi-local correcto)
    default_warehouse = models.ForeignKey(
        "core.Warehouse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_stores",
    )

    class Meta:
        unique_together = [("tenant", "name")]
        indexes = [
            models.Index(fields=["tenant", "name"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} (tenant={self.tenant_id})"
