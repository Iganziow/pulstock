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
    """Non-sale cash in/out during a session (e.g. expenses, fund additions).

    Daniel 01/05/26 — agregado `category` para clasificar gastos/ingresos
    y poder mostrar reportes "en qué se va la plata". Fudo no tiene esto
    (solo permite descripción libre); con categorías Pulstock puede dar
    al dueño un breakdown automático de gastos por tipo.
    """
    TYPE_IN  = "IN"
    TYPE_OUT = "OUT"
    TYPE_CHOICES = [(TYPE_IN, "Ingreso"), (TYPE_OUT, "Egreso")]

    # Categorías opcionales para clasificar movimientos.
    # Cada categoría aplica naturalmente a un tipo (IN/OUT), pero NO se
    # valida cross-fielde — el frontend muestra solo las relevantes según
    # el `type` que el usuario eligió.
    CAT_SUPPLIER       = "SUPPLIER"        # OUT: Pago a proveedor
    CAT_SALARY         = "SALARY"          # OUT: Sueldo / pago al equipo
    CAT_SERVICE        = "SERVICE"         # OUT: Servicios (luz, agua, internet)
    CAT_OWNER_DRAW     = "OWNER_DRAW"      # OUT: Retiro del dueño
    CAT_REFUND         = "REFUND"          # OUT: Devolución a cliente
    CAT_OTHER_OUT      = "OTHER_OUT"       # OUT: Otro egreso
    CAT_CAPITAL        = "CAPITAL"         # IN:  Aporte de capital del dueño
    CAT_EXTRA_INCOME   = "EXTRA_INCOME"    # IN:  Recaudación adicional / cobro extra
    CAT_LOAN           = "LOAN"            # IN:  Préstamo recibido
    CAT_OTHER_IN       = "OTHER_IN"        # IN:  Otro ingreso
    CAT_UNCATEGORIZED  = ""                # Default — para compat con movs viejos

    CATEGORY_CHOICES = [
        (CAT_UNCATEGORIZED, "Sin categoría"),
        # Egresos
        (CAT_SUPPLIER,     "Pago a proveedor"),
        (CAT_SALARY,       "Sueldo"),
        (CAT_SERVICE,      "Servicio (luz/agua/internet)"),
        (CAT_OWNER_DRAW,   "Retiro del dueño"),
        (CAT_REFUND,       "Devolución a cliente"),
        (CAT_OTHER_OUT,    "Otro egreso"),
        # Ingresos
        (CAT_CAPITAL,      "Aporte de capital"),
        (CAT_EXTRA_INCOME, "Recaudación adicional"),
        (CAT_LOAN,         "Préstamo"),
        (CAT_OTHER_IN,     "Otro ingreso"),
    ]

    # Mapeo helper: qué categorías son IN vs OUT
    CATEGORIES_IN = {CAT_CAPITAL, CAT_EXTRA_INCOME, CAT_LOAN, CAT_OTHER_IN}
    CATEGORIES_OUT = {CAT_SUPPLIER, CAT_SALARY, CAT_SERVICE, CAT_OWNER_DRAW, CAT_REFUND, CAT_OTHER_OUT}

    tenant      = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="cash_movements")
    session     = models.ForeignKey(CashSession, on_delete=models.CASCADE, related_name="movements")
    type        = models.CharField(max_length=3, choices=TYPE_CHOICES)
    category    = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, blank=True, default="",
        help_text="Categoría opcional. Permite reportes de gastos/ingresos por tipo.",
    )
    amount      = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    created_by  = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="cash_movements")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "session"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "type", "category"]),
        ]

    def __str__(self):
        return f"CashMovement #{self.id} {self.type} {self.amount}"
