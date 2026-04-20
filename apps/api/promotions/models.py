from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import Tenant, User


class Promotion(models.Model):
    """Oferta/promoción temporal con descuento % o precio fijo."""

    TYPE_PCT = "pct"
    TYPE_FIXED = "fixed_price"
    DISCOUNT_TYPE_CHOICES = [
        (TYPE_PCT, "Porcentaje"),
        (TYPE_FIXED, "Precio fijo"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="promotions")
    name = models.CharField(max_length=200)
    discount_type = models.CharField(max_length=12, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Porcentaje (ej: 30.00 para 30%) o precio fijo promocional",
    )

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "is_active", "start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_discount_type_display()} {self.discount_value})"

    @property
    def status(self):
        now = timezone.now()
        if not self.is_active:
            return "inactive"
        if now < self.start_date:
            return "scheduled"
        if now > self.end_date:
            return "expired"
        return "active"

    def compute_promo_price(self, original_price, override_value=None):
        """Calcula el precio promocional dado un precio original.

        IMPORTANTE: usamos `is not None` en vez de `or` porque override_value=0
        es un valor válido (producto gratis como promo, o 0% descuento).
        """
        value = override_value if override_value is not None else self.discount_value
        if self.discount_type == self.TYPE_PCT:
            return (original_price * (Decimal("1") - value / Decimal("100"))).quantize(Decimal("1"))
        return value  # fixed_price


class PromotionProduct(models.Model):
    """Productos incluidos en una promoción."""

    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="promotion_items")
    override_discount_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Override del valor de descuento para este producto específico",
    )

    class Meta:
        unique_together = [("promotion", "product")]
        indexes = [
            models.Index(fields=["product", "promotion"]),
        ]

    def __str__(self):
        return f"Promo '{self.promotion.name}' → {self.product_id}"
