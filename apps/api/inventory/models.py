# inventory/models.py
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


# =========================================================
# STOCK ACTUAL POR BODEGA
# =========================================================
class StockItem(models.Model):
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("core.Warehouse", on_delete=models.PROTECT)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)

    on_hand = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    updated_at = models.DateTimeField(auto_now=True)

    # ✅ costo promedio ponderado (por bodega)
    avg_cost = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))

    # ✅ valorización persistida (on_hand * avg_cost, mantenida por lógica)
    stock_value = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    class Meta:
        unique_together = [("tenant", "warehouse", "product")]
        indexes = [
            models.Index(fields=["tenant", "warehouse", "product"]),
            models.Index(fields=["tenant", "warehouse"]),
            models.Index(fields=["tenant", "product"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(on_hand__gte=0),
                name="stockitem_on_hand_gte_0",
            )
        ]

    def __str__(self) -> str:
        return (
            f"StockItem("
            f"t={self.tenant_id}, "
            f"wh={self.warehouse_id}, "
            f"p={self.product_id}, "
            f"on_hand={self.on_hand})"
        )


# =========================================================
# MOVIMIENTOS DE STOCK (KARDEX / AUDITORÍA)
# =========================================================
class StockMove(models.Model):
    IN = "IN"
    OUT = "OUT"
    ADJ = "ADJ"

    MOVE_TYPES = [
        (IN, "IN"),
        (OUT, "OUT"),
        (ADJ, "ADJ"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("core.Warehouse", on_delete=models.PROTECT)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)

    # Auditoría
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_moves",
    )

    move_type = models.CharField(max_length=3, choices=MOVE_TYPES)
    qty = models.DecimalField(max_digits=12, decimal_places=3)

    # costo unitario ingresado (solo aplica típicamente a IN / RECEIVE o IN en TRANSFER)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    # ✅ snapshot del costo usado para valorizar el movimiento (para auditoría)
    cost_snapshot = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    # ✅ impacto en valorización (positivo en IN, negativo en OUT)
    value_delta = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    # Motivo tipificado
    reason = models.CharField(max_length=32, blank=True, default="")

    # Referencia documental (venta, transferencia, ajuste, etc.)
    ref_type = models.CharField(max_length=32, null=True, blank=True)
    ref_id = models.PositiveIntegerField(null=True, blank=True)

    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "warehouse", "product", "created_at"]),
            models.Index(fields=["tenant", "ref_type", "ref_id"]),
            models.Index(fields=["tenant", "warehouse", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"StockMove("
            f"{self.move_type} "
            f"t={self.tenant_id} "
            f"wh={self.warehouse_id} "
            f"p={self.product_id} "
            f"qty={self.qty})"
        )


# =========================================================
# TRANSFERENCIA ENTRE BODEGAS (CABECERA)
# =========================================================
class StockTransfer(models.Model):
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)

    from_warehouse = models.ForeignKey(
        "core.Warehouse",
        on_delete=models.PROTECT,
        related_name="transfers_out",
    )

    to_warehouse = models.ForeignKey(
        "core.Warehouse",
        on_delete=models.PROTECT,
        related_name="transfers_in",
    )

    note = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_transfers",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "from_warehouse"]),
            models.Index(fields=["tenant", "to_warehouse"]),
        ]

    def __str__(self):
        return f"Transfer #{self.id} (wh {self.from_warehouse_id} → {self.to_warehouse_id})"


# =========================================================
# LÍNEAS DE TRANSFERENCIA
# =========================================================
class StockTransferLine(models.Model):
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)

    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name="lines",
    )

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)

    qty = models.DecimalField(max_digits=12, decimal_places=3)

    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "transfer"]),
            models.Index(fields=["tenant", "product"]),
        ]

    def __str__(self):
        return (
            f"TransferLine #{self.id} "
            f"(transfer={self.transfer_id}, "
            f"product={self.product_id}, "
            f"qty={self.qty})"
        )
