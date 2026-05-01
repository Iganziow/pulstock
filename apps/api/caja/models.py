"""
caja/models.py
==============
Cash register management: sessions (arqueo) and manual movements.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone


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


class MovementCategory(models.Model):
    """
    Categoría personalizable de movimientos de caja, por tenant.
    Daniel 01/05/26: las categorías ya NO son hardcoded — cada negocio
    puede crear/editar/desactivar las suyas.

    Soft-delete via `is_active=False`: los movimientos viejos siguen
    referenciando la categoría aunque se "borre" (preserva historia).

    Las categorías default del sistema (is_default_template=True) se
    crean automáticamente para cada Tenant nuevo en migration. El dueño
    puede desactivarlas si no le sirven (ej. "Préstamo" si nunca toma).
    """
    TYPE_IN   = "IN"
    TYPE_OUT  = "OUT"
    TYPE_BOTH = "BOTH"
    TYPE_CHOICES = [
        (TYPE_IN,   "Ingreso"),
        (TYPE_OUT,  "Egreso"),
        (TYPE_BOTH, "Ambos"),
    ]

    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE,
        related_name="movement_categories",
    )
    code = models.SlugField(
        max_length=40,
        help_text="Identificador interno (auto-generado del label si está vacío)",
    )
    label = models.CharField(max_length=80)
    type = models.CharField(max_length=4, choices=TYPE_CHOICES, default=TYPE_OUT)
    icon = models.CharField(
        max_length=8, blank=True, default="",
        help_text="Emoji opcional (🛒 💰 etc.)",
    )
    color = models.CharField(
        max_length=9, blank=True, default="",
        help_text="Color hex opcional (#FF0000 o #FF0000FF)",
    )
    # Marcador de plantilla del sistema. NO afecta visibilidad ni
    # permisos — solo permite identificar las creadas por seeder al
    # crear un Tenant nuevo (para versionar / actualizar plantillas).
    is_default_template = models.BooleanField(default=False)
    # Soft-delete: si False, NO aparece en listados / dropdowns.
    # Movimientos antiguos siguen apuntando a la categoría — historia preservada.
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["type", "order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_movement_category_code_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "type"]),
        ]

    def __str__(self):
        return f"MovCat #{self.id} t={self.tenant_id} {self.code}={self.label}"


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
    # Daniel 01/05/26 — categoría legacy (CharField hardcoded). Mantener por
    # backward compat con código existente. Nuevo source of truth: category_fk.
    category    = models.CharField(
        max_length=40, choices=CATEGORY_CHOICES, blank=True, default="",
        help_text="DEPRECATED: usar category_fk. Mantenido por compat.",
    )
    # Nuevo FK personalizable. Si está set, gana sobre `category` string.
    # Soft-delete protege historia: aunque la categoría se "desactive",
    # los movimientos viejos siguen mostrando su label original.
    category_fk = models.ForeignKey(
        "MovementCategory",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="movements",
        help_text="Categoría personalizable del tenant (FK a MovementCategory).",
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
