# sales/models.py
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Sale(models.Model):
    STATUS_COMPLETED = "COMPLETED"
    STATUS_VOID = "VOID"

    STATUS_CHOICES = [
        (STATUS_COMPLETED, "COMPLETED"),
        (STATUS_VOID, "VOID"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)

    # Store activo (mismo concepto que inventory)
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.PROTECT,
        related_name="sales",
    )

    # Bodega desde la cual se vendió (muy bien que exista)
    warehouse = models.ForeignKey("core.Warehouse", on_delete=models.PROTECT)

    created_by = models.ForeignKey("core.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    # Totales venta (precio de venta)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # ✅ COSTEO (B: promedio ponderado)
    # total_cost = suma de (line_cost) en SaleLine
    total_cost = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    # gross_profit = total - total_cost  (o subtotal - total_cost, según tu lógica)
    gross_profit = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_COMPLETED)

    SALE_TYPE_VENTA = "VENTA"
    SALE_TYPE_CONSUMO = "CONSUMO_INTERNO"
    SALE_TYPE_CHOICES = [
        (SALE_TYPE_VENTA, "Venta"),
        (SALE_TYPE_CONSUMO, "Consumo Interno"),
    ]

    sale_type = models.CharField(
        max_length=20, choices=SALE_TYPE_CHOICES,
        default=SALE_TYPE_VENTA, db_index=True,
    )

    # Clave de idempotencia opcional — si se provee, previene duplicados por reintento del cliente
    idempotency_key = models.CharField(max_length=64, blank=True, default="")

    # Número de venta por tenant (empieza en 1 para cada negocio)
    sale_number = models.PositiveIntegerField(null=True, blank=True)

    # Propina voluntaria — NO incluida en total ni gross_profit
    tip = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Sesión de caja abierta al momento de la venta (nullable para compatibilidad)
    cash_session = models.ForeignKey(
        "caja.CashSession", on_delete=models.SET_NULL, null=True, blank=True, related_name="sales"
    )

    # Comanda de mesa asociada (nullable — ventas POS directas no tienen mesa)
    open_order = models.ForeignKey(
        "tables.OpenOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="sales"
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "store", "created_at"]),
            models.Index(fields=["tenant", "warehouse", "created_at"]),
            models.Index(fields=["tenant", "idempotency_key"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "sale_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "store", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="unique_sale_idempotency_key_per_store",
            ),
            models.UniqueConstraint(
                fields=["tenant", "sale_number"],
                condition=~Q(sale_number=None),
                name="unique_sale_number_per_tenant",
            ),
        ]

    def __str__(self):
        return f"Sale #{self.id} (tenant={self.tenant_id}, wh={self.warehouse_id})"


class TenantSaleCounter(models.Model):
    """
    Atomic counter for sale_number per tenant.
    Uses select_for_update() + F() to guarantee no duplicates
    even under concurrent transactions.
    """
    tenant = models.OneToOneField(
        "core.Tenant", on_delete=models.CASCADE, primary_key=True,
        related_name="sale_counter",
    )
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "sales_tenantsalecounter"

    def __str__(self):
        return f"SaleCounter tenant={self.tenant_id} last={self.last_number}"


class SalePayment(models.Model):
    METHOD_CASH     = "cash"
    METHOD_CARD     = "card"       # Tarjeta crédito
    METHOD_DEBIT    = "debit"      # Tarjeta débito
    METHOD_TRANSFER = "transfer"
    METHOD_CHOICES  = [
        (METHOD_CASH,     "Efectivo"),
        (METHOD_CARD,     "Tarjeta Crédito"),
        (METHOD_DEBIT,    "Tarjeta Débito"),
        (METHOD_TRANSFER, "Transferencia"),
    ]

    sale   = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=["sale"]),
        ]

    def __str__(self):
        return f"SalePayment sale={self.sale_id} {self.method}={self.amount}"


class SaleLine(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)

    qty = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    # Total precio venta por línea
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # ✅ COSTO promedio ponderado capturado al momento de vender
    # Esto sale desde StockItem.avg_cost de ESA bodega al confirmar la venta
    unit_cost_snapshot = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))

    # qty * unit_cost_snapshot (para poder auditar sin recalcular)
    line_cost = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    # (line_total - line_cost) como métrica rápida
    line_gross_profit = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    # ── Promociones ──
    promotion = models.ForeignKey(
        "promotions.Promotion", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sale_lines",
    )
    original_unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Precio original sin descuento",
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Descuento total aplicado en esta línea",
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "product"]),
            models.Index(fields=["tenant", "sale"]),
        ]

    def __str__(self):
        return f"SaleLine #{self.id} (sale={self.sale_id}, product={self.product_id}, qty={self.qty})"
