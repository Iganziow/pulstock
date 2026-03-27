# purchases/models.py
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings


class Purchase(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_POSTED = "POSTED"
    STATUS_VOID = "VOID"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "DRAFT"),
        (STATUS_POSTED, "POSTED"),
        (STATUS_VOID, "VOID"),
    ]

    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)

    # store activo (mismo concepto que ventas/inventory)
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.PROTECT,
        related_name="purchases",
    )

    # 1 factura = 1 bodega (por ahora)
    warehouse = models.ForeignKey("core.Warehouse", on_delete=models.PROTECT)

    # Proveedor opcional (MVP)
    supplier_name = models.CharField(max_length=255, blank=True, default="")

    # Datos opcionales de documento
    invoice_number = models.CharField(max_length=64, blank=True, default="")
    invoice_date = models.DateField(null=True, blank=True)

    note = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    # Totales de COSTO (CLP, sin moneda por ahora)
    subtotal_cost = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))  # opcional
    total_cost = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "store", "created_at"]),
            models.Index(fields=["tenant", "warehouse", "created_at"]),
            models.Index(fields=["tenant", "status", "created_at"]),
        ]

    def __str__(self):
        return f"Purchase #{self.id} (tenant={self.tenant_id}, wh={self.warehouse_id}, status={self.status})"


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)

    qty = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=3)

    # qty * unit_cost (auditable)
    line_total_cost = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "product"]),
            models.Index(fields=["tenant", "purchase"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(qty__gt=0),
                name="purchaseline_qty_positive",
            ),
            models.CheckConstraint(
                check=models.Q(unit_cost__gte=0),
                name="purchaseline_unit_cost_non_negative",
            ),
        ]

    def __str__(self):
        return f"PurchaseLine #{self.id} (purchase={self.purchase_id}, product={self.product_id}, qty={self.qty})"


# ✅ PROXY: para que exista PurchaseInvoice sin crear tabla nueva
class PurchaseInvoice(Purchase):
    class Meta:
        proxy = True
        verbose_name = "Purchase Invoice"
        verbose_name_plural = "Purchase Invoices"


class PurchaseInvoiceLine(models.Model):
    invoice = models.ForeignKey(
        "purchases.PurchaseInvoice",
        on_delete=models.CASCADE,
        related_name="invoice_lines",
    )

    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.PROTECT,
    )

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
    )

    qty = models.DecimalField(max_digits=12, decimal_places=3)

    # costo unitario de compra
    unit_cost = models.DecimalField(max_digits=12, decimal_places=3)

    line_total_cost = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
    )

    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "product"]),
            models.Index(fields=["tenant", "invoice"]),
        ]

    def __str__(self):
        return f"InvoiceLine #{self.id} (product={self.product_id}, qty={self.qty})"


class Supplier(models.Model):
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.PROTECT,
        related_name="suppliers",
    )

    name = models.CharField(max_length=255)
    rut = models.CharField(max_length=32, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "name"]),
        ]

    def __str__(self):
        return self.name
