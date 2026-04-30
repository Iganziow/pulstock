"""
caja/models.py
==============
Cash register management: sessions (arqueo) and manual movements.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q


class CashRegister(models.Model):
    """A physical cash register in a store."""
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="cash_registers")
    store  = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="cash_registers")
    name   = models.CharField(max_length=60)       # "Caja 1", "Barra"
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("tenant", "store", "name")]
        indexes = [models.Index(fields=["tenant", "store"])]

    def __str__(self):
        return f"{self.name} (store={self.store_id})"


class CashSession(models.Model):
    """An arqueo (shift) tied to a CashRegister."""
    STATUS_OPEN   = "OPEN"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [(STATUS_OPEN, "Abierta"), (STATUS_CLOSED, "Cerrada")]

    tenant   = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="cash_sessions")
    store    = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="cash_sessions")
    register = models.ForeignKey(CashRegister, on_delete=models.PROTECT, related_name="sessions")
    status   = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)

    opened_by = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="opened_sessions")
    opened_at = models.DateTimeField(auto_now_add=True)

    initial_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    closed_by    = models.ForeignKey("core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="closed_sessions")
    closed_at    = models.DateTimeField(null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Efectivo contado por el cajero al cierre")
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Calculado al cierre")
    difference   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="counted - expected")
    note         = models.TextField(blank=True, default="")

    # Snapshot inmutable del summary completo al momento del cierre.
    # Daniel 29/04/26 — caso real Marbrava: si Mario cierra la caja con
    # tip_total=$1.500 y al día siguiente edita la propina de una venta
    # de ayer a $5.000, el ARQUEO HISTÓRICO debe seguir mostrando $1.500
    # (lo que se contó al cierre). Sin este snapshot el `live` se
    # recalcula con datos actuales y muta el reporte cerrado — eso es
    # exactamente lo que Fudo blinda con "una vez cerrado el arqueo no
    # se puede reabrir".
    #
    # Estructura: dict completo con todas las keys del _session_summary
    # (cash_sales, debit_sales, ..., tips_by_method, expected_cash, etc.).
    closing_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "store", "status"])]
        constraints = [
            # Only one OPEN session per register at a time
            models.UniqueConstraint(
                fields=["tenant", "register"],
                condition=Q(status="OPEN"),
                name="unique_open_session_per_register",
            )
        ]

    def __str__(self):
        return f"CashSession #{self.id} register={self.register_id} status={self.status}"


class CashMovement(models.Model):
    """Non-sale cash in/out during a session (e.g. expenses, fund additions)."""
    TYPE_IN  = "IN"
    TYPE_OUT = "OUT"
    TYPE_CHOICES = [(TYPE_IN, "Ingreso"), (TYPE_OUT, "Egreso")]

    tenant      = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="cash_movements")
    session     = models.ForeignKey(CashSession, on_delete=models.CASCADE, related_name="movements")
    type        = models.CharField(max_length=3, choices=TYPE_CHOICES)
    amount      = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    created_by  = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="cash_movements")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "session"])]

    def __str__(self):
        return f"CashMovement #{self.id} {self.type} {self.amount}"
