"""
Test dedupe_active_models — invariante 1 modelo activo por (product, warehouse).
BUGFIX 01/06/26: el swap derived/organic acumulaba modelos activos.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django.core.management import call_command

from catalog.models import Product
from forecast.models import ForecastModel


def _product(tenant, name):
    return Product.objects.create(tenant=tenant, name=name, price=Decimal("1000"), is_active=True)


def _model(tenant, warehouse, product, algo, wape, version, days_old=0):
    return ForecastModel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        algorithm=algo, version=version, model_params={}, metrics={"wape": wape},
        trained_at=timezone.now() - timedelta(days=days_old),
        data_points=30, demand_pattern="smooth", is_active=True,
        confidence_label="medium",
    )


@pytest.mark.django_db
class TestDedupeActiveModels:
    def test_keeps_lowest_wape(self, tenant, warehouse):
        p = _product(tenant, "Leche")
        # 3 modelos activos del mismo producto/warehouse (bug)
        _model(tenant, warehouse, p, "ingredient_derived", 80, 1)
        keep = _model(tenant, warehouse, p, "ingredient_derived", 25, 2)  # mejor WAPE
        _model(tenant, warehouse, p, "ingredient_derived", 60, 3)

        call_command("dedupe_active_models", "--tenant", str(tenant.id), "--apply")

        actives = ForecastModel.objects.filter(tenant=tenant, product=p, warehouse=warehouse, is_active=True)
        assert actives.count() == 1, "debe quedar 1 activo"
        assert actives.first().id == keep.id, "debe conservar el de menor WAPE"

    def test_dry_run_does_not_change(self, tenant, warehouse):
        p = _product(tenant, "Café")
        _model(tenant, warehouse, p, "theta", 50, 1)
        _model(tenant, warehouse, p, "ingredient_derived", 30, 2)
        call_command("dedupe_active_models", "--tenant", str(tenant.id))  # dry-run
        assert ForecastModel.objects.filter(tenant=tenant, product=p, is_active=True).count() == 2

    def test_single_active_untouched(self, tenant, warehouse):
        p = _product(tenant, "Azúcar")
        m = _model(tenant, warehouse, p, "moving_avg", 40, 1)
        call_command("dedupe_active_models", "--tenant", str(tenant.id), "--apply")
        m.refresh_from_db()
        assert m.is_active is True, "1 solo activo no debe tocarse"

    def test_separate_warehouses_kept(self, tenant, warehouse, warehouse_b):
        """Modelos del mismo producto en warehouses DISTINTOS son legítimos."""
        p = _product(tenant, "Té")
        m1 = _model(tenant, warehouse, p, "theta", 30, 1)
        m2 = _model(tenant, warehouse_b, p, "theta", 30, 1)
        call_command("dedupe_active_models", "--tenant", str(tenant.id), "--apply")
        m1.refresh_from_db(); m2.refresh_from_db()
        assert m1.is_active and m2.is_active, "1 por warehouse es correcto, no tocar"
