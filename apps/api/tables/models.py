"""
tables/models.py — Table management for café/restaurant orders.
"""
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Table(models.Model):
    STATUS_FREE = "FREE"
    STATUS_OPEN = "OPEN"
    STATUS_CHOICES = [
        (STATUS_FREE, "Libre"),
        (STATUS_OPEN, "Ocupada"),
    ]

    tenant    = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="tables")
    store     = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="tables")
    name      = models.CharField(max_length=60)
    capacity  = models.PositiveSmallIntegerField(default=4)
    status    = models.CharField(max_length=8, choices=STATUS_CHOICES, default=STATUS_FREE)
    is_active = models.BooleanField(default=True)
    zone      = models.CharField(max_length=60, blank=True, default="",
                    help_text="Zona del local: Salón Grande, Ventanas, etc.")
    is_counter = models.BooleanField(default=False,
                    help_text="True para posiciones de mostrador/para llevar")

    class Meta:
        unique_together = [("tenant", "store", "name")]
        indexes = [
            models.Index(fields=["tenant", "store", "status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class OpenOrder(models.Model):
    STATUS_OPEN   = "OPEN"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_OPEN,   "Abierta"),
        (STATUS_CLOSED, "Cerrada"),
    ]

    tenant    = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="open_orders")
    store     = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="open_orders")
    warehouse = models.ForeignKey("core.Warehouse", on_delete=models.PROTECT, related_name="open_orders")
    table     = models.ForeignKey(Table, on_delete=models.PROTECT, related_name="orders")
    status    = models.CharField(max_length=8, choices=STATUS_CHOICES, default=STATUS_OPEN)
    opened_by = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="opened_orders")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    customer_name = models.CharField(max_length=100, blank=True, default="")
    note      = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                condition=Q(status="OPEN"),
                fields=("tenant", "table"),
                name="unique_open_order_per_table",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "store", "status"]),
            models.Index(fields=["tenant", "table", "status"]),
        ]

    def __str__(self):
        return f"OpenOrder #{self.id} — {self.table} ({self.status})"


class OpenOrderLine(models.Model):
    tenant      = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="order_lines")
    order       = models.ForeignKey(OpenOrder, on_delete=models.CASCADE, related_name="lines")
    product     = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="order_lines")
    qty         = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price  = models.DecimalField(max_digits=12, decimal_places=2)
    note        = models.CharField(max_length=255, blank=True, default="")
    added_at    = models.DateTimeField(auto_now_add=True)
    added_by    = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="added_order_lines")
    is_paid     = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True, default="")
    paid_by_sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="paid_order_lines",
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "order"]),
            models.Index(fields=["tenant", "order", "is_paid"]),
        ]

    def __str__(self):
        return f"OrderLine #{self.id} (order={self.order_id}, product={self.product_id}, qty={self.qty})"
