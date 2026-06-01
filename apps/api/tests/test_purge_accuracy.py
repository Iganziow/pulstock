"""
Test F (3) — purgar accuracy contaminada de ingredientes (Mario 31/05/26).

Borra ForecastAccuracy de ingredientes anterior a trusted_from (el período de
subregistro). No toca: accuracy post-trusted_from, ni productos que no son
ingredientes.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product, Recipe, RecipeLine
from forecast.models import ForecastAccuracy


def _product(tenant, name):
    return Product.objects.create(tenant=tenant, name=name, price=Decimal("1000"), is_active=True)


def _acc(tenant, warehouse, product, d):
    return ForecastAccuracy.objects.create(
        tenant=tenant, warehouse=warehouse, product=product, date=d,
        qty_predicted=Decimal("10"), qty_actual=Decimal("5"), error=Decimal("5"),
        abs_pct_error=Decimal("100"), algorithm="theta", was_stockout=False,
    )


@pytest.mark.django_db
class TestPurgeContaminatedAccuracy:
    def _setup(self, tenant, warehouse):
        tenant.ingredient_forecast_trusted_from = date(2026, 5, 18)
        tenant.save(update_fields=["ingredient_forecast_trusted_from"])
        # Ingrediente (de receta activa) + producto normal (no ingrediente)
        leche = _product(tenant, "Leche")
        capu = _product(tenant, "Capuccino")
        recipe = Recipe.objects.create(tenant=tenant, product=capu, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=leche, qty=Decimal("0.2"))
        galleta = _product(tenant, "Galleta")  # NO es ingrediente
        # Accuracy: leche pre (contaminado) + post; galleta pre (no debe tocarse)
        _acc(tenant, warehouse, leche, date(2026, 5, 10))   # pre → borrar
        _acc(tenant, warehouse, leche, date(2026, 5, 15))   # pre → borrar
        _acc(tenant, warehouse, leche, date(2026, 5, 20))   # post → conservar
        _acc(tenant, warehouse, galleta, date(2026, 5, 10)) # no ingrediente → conservar
        return leche, galleta

    def test_dry_run_does_not_delete(self, tenant, warehouse):
        self._setup(tenant, warehouse)
        before = ForecastAccuracy.objects.count()
        call_command("purge_contaminated_accuracy", "--tenant", str(tenant.id))
        assert ForecastAccuracy.objects.count() == before, "dry-run no debe borrar"

    def test_apply_deletes_only_contaminated_ingredient(self, tenant, warehouse):
        leche, galleta = self._setup(tenant, warehouse)
        call_command("purge_contaminated_accuracy", "--tenant", str(tenant.id), "--apply")
        # Leche pre-18/05 borrados (2), leche post conservado (1)
        assert ForecastAccuracy.objects.filter(product=leche).count() == 1
        assert ForecastAccuracy.objects.filter(product=leche, date=date(2026, 5, 20)).exists()
        # Galleta (no ingrediente) intacta
        assert ForecastAccuracy.objects.filter(product=galleta).count() == 1

    def test_no_trusted_from_skips(self, tenant, warehouse):
        # Sin trusted_from → no borra nada
        tenant.ingredient_forecast_trusted_from = None
        tenant.save(update_fields=["ingredient_forecast_trusted_from"])
        leche = _product(tenant, "Leche2")
        capu = _product(tenant, "Capu2")
        r = Recipe.objects.create(tenant=tenant, product=capu, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche, qty=Decimal("0.2"))
        _acc(tenant, warehouse, leche, date(2026, 5, 10))
        call_command("purge_contaminated_accuracy", "--tenant", str(tenant.id), "--apply")
        assert ForecastAccuracy.objects.filter(product=leche).count() == 1
