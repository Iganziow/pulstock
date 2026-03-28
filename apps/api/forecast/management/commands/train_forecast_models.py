"""
train_forecast_models
=====================
Nightly cron (03:00): trains forecast models for all products.
Orchestrates the pipeline — business logic lives in forecast.services.

Usage:
    python manage.py train_forecast_models
    python manage.py train_forecast_models --tenant 1
    python manage.py train_forecast_models --product 42
    python manage.py train_forecast_models --horizon 14
"""
from datetime import date

from django.core.management.base import BaseCommand

from core.models import Tenant
from catalog.models import Product
from inventory.models import StockItem
from forecast.models import DailySales
from forecast.services import train_product_model, train_sparse_product
from forecast.models import CategoryDemandProfile


class Command(BaseCommand):
    help = "Train forecast models (auto-selects best algorithm per product)"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Specific tenant ID")
        parser.add_argument("--product", type=int, help="Specific product ID")
        parser.add_argument("--min-days", type=int, default=14, help="Min days of data (default: 14)")
        parser.add_argument("--horizon", type=int, default=14, help="Forecast horizon in days (default: 14)")
        parser.add_argument("--window", type=int, default=21, help="Moving average window (default: 21)")

    # Parámetros ajustados por tipo de negocio
    BUSINESS_PROFILES = {
        # Retail/minimarket: ítems de alta rotación, ventana corta, respuesta rápida
        "retail":      {"window": 14, "min_days": 14, "horizon": 30, "shrinkage_k": 14},
        # Restaurant/cafetería: demanda muy estacional por día de semana, horizonte corto
        "restaurant":  {"window": 7,  "min_days": 10, "horizon": 21, "shrinkage_k": 7},
        # Ferretería: ítems de baja rotación, proyectos, ventana larga
        "hardware":    {"window": 30, "min_days": 21, "horizon": 60, "shrinkage_k": 21},
        # Distribuidora: volumen alto, demanda regular, horizonte medio-largo
        "wholesale":   {"window": 21, "min_days": 14, "horizon": 45, "shrinkage_k": 14},
        # Farmacia: similar a retail pero con patrones de receta/estacionalidad
        "pharmacy":    {"window": 14, "min_days": 14, "horizon": 30, "shrinkage_k": 14},
        # Genérico
        "other":       {"window": 21, "min_days": 14, "horizon": 30, "shrinkage_k": 14},
    }

    def handle(self, *args, **options):
        today = date.today()

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        stats = {"trained": 0, "skipped": 0, "improved": 0, "kept": 0,
                 "by_algo": {}}

        for tenant in tenants:
            # Use business-type profile unless explicitly overridden via CLI
            profile = self.BUSINESS_PROFILES.get(
                getattr(tenant, "business_type", "other") or "other",
                self.BUSINESS_PROFILES["other"],
            )
            min_days = max(7, options["min_days"] if options["min_days"] != 14 else profile["min_days"])
            horizon  = max(1, min(90, options["horizon"] if options["horizon"] != 14 else profile["horizon"]))
            window   = max(7, options["window"] if options["window"] != 21 else profile["window"])
            shrinkage_k = profile.get("shrinkage_k", 14)
            self._process_tenant(tenant, today, min_days, horizon, window,
                                 options.get("product"), stats, shrinkage_k=shrinkage_k)

        algo_summary = ", ".join(f"{k}={v}" for k, v in stats["by_algo"].items())
        self.stdout.write(self.style.SUCCESS(
            f"Done: {stats['trained']} new, {stats['improved']} improved, "
            f"{stats['kept']} kept, {stats['skipped']} skipped. "
            f"Algorithms: {algo_summary or 'none'}"
        ))

    def _process_tenant(self, tenant, today, min_days, horizon, window,
                        product_id, stats, shrinkage_k=14):
        # Clean up: deactivate forecast models for discontinued products
        from forecast.models import ForecastModel as FM
        deactivated = FM.objects.filter(
            tenant=tenant, product__is_active=False, is_active=True
        ).update(is_active=False)
        if deactivated:
            from forecast.models import Forecast
            Forecast.objects.filter(
                tenant=tenant, model__product__is_active=False, forecast_date__gt=today
            ).delete()

        products = Product.objects.filter(tenant=tenant, is_active=True)
        if product_id:
            products = products.filter(id=product_id)

        stock_items = {
            (si.warehouse_id, si.product_id): si
            for si in StockItem.objects.filter(tenant=tenant, product__in=products)
        }

        # Load category profiles for sparse-data products
        category_profiles = {
            (cp.category_id, cp.warehouse_id): cp
            for cp in CategoryDemandProfile.objects.filter(tenant=tenant)
        }

        # All warehouse IDs that have stock for this tenant
        all_wh_ids = set(
            StockItem.objects.filter(tenant=tenant)
            .values_list("warehouse_id", flat=True).distinct()
        )

        trained_keys = set()  # (product_id, warehouse_id) already processed

        # Batch: fetch (product_id, warehouse_id, count) in one query
        from django.db.models import Count
        daily_stats = (
            DailySales.objects.filter(tenant=tenant, product__in=products)
            .values("product_id", "warehouse_id")
            .annotate(n_days=Count("id"))
        )
        # Map: product_id → [(warehouse_id, n_days), ...]
        product_wh_days = {}
        for row in daily_stats:
            product_wh_days.setdefault(row["product_id"], []).append(
                (row["warehouse_id"], row["n_days"])
            )

        for product in products:
            wh_entries = product_wh_days.get(product.id, [])
            for wh_id, n_days in wh_entries:
                trained_keys.add((product.id, wh_id))

                if n_days >= min_days:
                    train_product_model(
                        tenant, product, wh_id, today,
                        min_days, horizon, window, stock_items, stats,
                    )
                else:
                    # Sparse data: use category prior
                    train_sparse_product(
                        tenant, product, wh_id, today,
                        horizon, stock_items, category_profiles, stats,
                        shrinkage_k=shrinkage_k,
                    )

            # Products with stock but NO DailySales at all
            for wh_id in all_wh_ids:
                if (product.id, wh_id) in trained_keys:
                    continue
                si = stock_items.get((wh_id, product.id))
                if si and si.on_hand > 0:
                    trained_keys.add((product.id, wh_id))
                    train_sparse_product(
                        tenant, product, wh_id, today,
                        horizon, stock_items, category_profiles, stats,
                        shrinkage_k=shrinkage_k,
                    )
