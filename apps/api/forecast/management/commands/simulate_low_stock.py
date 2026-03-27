"""
simulate_low_stock
==================
Reduces stock of selected products to trigger forecast alerts and suggestions.

Usage:
    python manage.py simulate_low_stock                    # auto-select products
    python manage.py simulate_low_stock --tenant 1
    python manage.py simulate_low_stock --products 5,12,23 # specific product IDs
"""
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import F

from core.models import Tenant
from inventory.models import StockItem
from forecast.models import ForecastModel


class Command(BaseCommand):
    help = "Reduce stock on products to simulate stockout alerts"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Specific tenant ID")
        parser.add_argument("--products", type=str, help="Comma-separated product IDs")

    def handle(self, *args, **options):
        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        specific_ids = None
        if options["products"]:
            specific_ids = [int(x.strip()) for x in options["products"].split(",")]

        for tenant in tenants:
            self._process(tenant, specific_ids)

        self.stdout.write("\n  🚀 Ahora re-entrena y genera sugerencias:")
        self.stdout.write("     python manage.py train_forecast_models")
        self.stdout.write("     python manage.py generate_purchase_suggestions")

    def _process(self, tenant, specific_ids):
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Tenant: {tenant.id}")
        self.stdout.write(f"{'='*60}")

        # Get products with active forecast models
        active_models = ForecastModel.objects.filter(
            tenant=tenant, is_active=True
        ).select_related("product")

        if specific_ids:
            active_models = active_models.filter(product_id__in=specific_ids)

        if not active_models.exists():
            self.stdout.write(self.style.WARNING("  No active forecast models found"))
            return

        models_list = list(active_models)

        if not specific_ids:
            # Auto-select: pick ~40% of products for different scenarios
            random.shuffle(models_list)
            count = max(3, len(models_list) * 4 // 10)
            models_list = models_list[:count]

        self.stdout.write(f"  Adjusting stock for {len(models_list)} products:\n")

        for i, fm in enumerate(models_list):
            product = fm.product
            params = fm.model_params or {}
            avg_daily = float(params.get("avg_daily", "5"))
            if avg_daily <= 0:
                avg_daily = 3.0

            # Assign different urgency levels
            if i % 5 == 0:
                # CRITICAL: 0-2 days of stock
                days_stock = random.uniform(0, 2)
                label = "CRITICAL (0-2 días)"
            elif i % 5 == 1:
                # HIGH: 3-5 days
                days_stock = random.uniform(3, 5)
                label = "HIGH (3-5 días)"
            elif i % 5 == 2:
                # MEDIUM: 6-10 days
                days_stock = random.uniform(6, 10)
                label = "MEDIUM (6-10 días)"
            elif i % 5 == 3:
                # AGOTADO: 0 stock
                days_stock = 0
                label = "AGOTADO (0 stock)"
            else:
                # LOW: 11-14 days
                days_stock = random.uniform(11, 14)
                label = "LOW (11-14 días)"

            new_stock = Decimal(str(round(avg_daily * days_stock, 0)))
            new_stock = max(Decimal("0"), new_stock)

            # Get current stock item
            si = StockItem.objects.filter(
                tenant=tenant, product=product, warehouse_id=fm.warehouse_id
            ).first()

            if not si:
                continue

            old_stock = si.on_hand
            avg_cost = si.avg_cost or Decimal("0")

            StockItem.objects.filter(id=si.id).update(
                on_hand=new_stock,
                stock_value=(new_stock * avg_cost).quantize(Decimal("0.01")),
            )

            self.stdout.write(
                f"  {product.name[:35]:35s} | "
                f"vta/día={avg_daily:5.1f} | "
                f"stock: {old_stock:>6.0f} → {new_stock:>4.0f} | "
                f"{label}"
            )

        self.stdout.write(f"\n  ✅ {len(models_list)} productos ajustados")