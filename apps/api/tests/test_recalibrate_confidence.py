"""
Tests del comando recalibrate_confidence (13/05/26).

Mario reportó que el sistema marcaba productos como "medium" cuando
el MAPE real era 129%. La calibración usaba el MAPE del backtest, no
el WAPE de producción. Este comando recalcula confidence_label con
el WAPE real de los últimos N días.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product
from core.models import Warehouse
from forecast.models import ForecastModel, ForecastAccuracy
from forecast.management.commands.recalibrate_confidence import (
    label_from_wape,
)


class TestLabelFromWape:
    """Pruebas unitarias del helper de mapeo."""

    def test_high_when_wape_under_30(self):
        assert label_from_wape(20.0) == "high"
        assert label_from_wape(29.99) == "high"

    def test_medium_when_wape_30_to_50(self):
        assert label_from_wape(30.0) == "medium"
        assert label_from_wape(49.99) == "medium"

    def test_low_when_wape_50_to_80(self):
        assert label_from_wape(50.0) == "low"
        assert label_from_wape(79.99) == "low"

    def test_very_low_when_wape_80_or_more(self):
        assert label_from_wape(80.0) == "very_low"
        assert label_from_wape(150.0) == "very_low"
        assert label_from_wape(550.0) == "very_low"

    def test_no_data_defaults_low(self):
        """Sin WAPE histórico → low (conservador, no asumir alta calidad)."""
        assert label_from_wape(None) == "low"


@pytest.mark.django_db
class TestRecalibrationCommand:

    @pytest.fixture
    def setup(self, tenant, store):
        warehouse = Warehouse.objects.create(tenant=tenant, store=store, name="W-cal")
        product = Product.objects.create(
            tenant=tenant, name="Producto cal", price=Decimal("1000"), is_active=True,
        )
        # Modelo activo con confidence "medium" (asumiendo del backtest)
        model = ForecastModel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            algorithm="simple_avg", version=1, is_active=True,
            model_params={"avg_daily": "10"},
            data_points=14, demand_pattern="smooth",
            confidence_label="medium",
            confidence_reason="MAPE backtest 35%",
        )
        return tenant, product, warehouse, model

    def _seed_accuracy(self, tenant, product, warehouse, days_data):
        """days_data: lista de (predicted, actual) para los últimos N días."""
        today = date.today()
        for i, (pred, actual) in enumerate(days_data):
            d = today - timedelta(days=i + 1)
            actual_dec = Decimal(str(actual))
            pred_dec = Decimal(str(pred))
            error = pred_dec - actual_dec
            abs_pct = None
            if actual_dec > 0:
                abs_pct = (abs(error) / actual_dec * 100).quantize(Decimal("0.01"))
            ForecastAccuracy.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=d,
                qty_predicted=pred_dec,
                qty_actual=actual_dec,
                error=error,
                abs_pct_error=abs_pct,
                algorithm="simple_avg",
                was_stockout=False,
            )

    def test_high_label_when_predictions_accurate(self, setup):
        """Predicciones casi perfectas (WAPE ~5%) → high."""
        tenant, product, warehouse, model = setup
        # 5 días con predicción muy cercana al real
        self._seed_accuracy(tenant, product, warehouse, [
            (10, 10), (12, 11), (8, 9), (10, 11), (10, 10),
        ])
        # WAPE = (0+1+1+1+0) / (10+11+9+11+10) * 100 = 3/51 * 100 ≈ 5.9%
        call_command("recalibrate_confidence", tenant=tenant.id, verbosity=0)
        model.refresh_from_db()
        assert model.confidence_label == "high"
        assert "WAPE real" in model.confidence_reason

    def test_medium_label_when_moderate_wape(self, setup):
        """WAPE ~40% → medium."""
        tenant, product, warehouse, model = setup
        # 5 días con error moderado
        self._seed_accuracy(tenant, product, warehouse, [
            (10, 7), (15, 10), (8, 5), (12, 8), (10, 7),
        ])
        # WAPE = (3+5+3+4+3) / (7+10+5+8+7) * 100 = 18/37 * 100 ≈ 48.6%
        call_command("recalibrate_confidence", tenant=tenant.id, verbosity=0)
        model.refresh_from_db()
        assert model.confidence_label == "medium"

    def test_very_low_when_wape_huge(self, setup):
        """Caso real de Mario: el sistema decía 'medium' pero MAPE real
        129%. Ahora debería ser very_low."""
        tenant, product, warehouse, model = setup
        # Predicciones masivamente más altas que la realidad
        self._seed_accuracy(tenant, product, warehouse, [
            (50, 1), (50, 2), (50, 1), (50, 2),
        ])
        # WAPE = (49+48+49+48) / (1+2+1+2) * 100 = 194/6 * 100 ≈ 3233%
        call_command("recalibrate_confidence", tenant=tenant.id, verbosity=0)
        model.refresh_from_db()
        assert model.confidence_label == "very_low"

    def test_default_low_when_no_accuracy_data(self, setup):
        """Sin ForecastAccuracy → defaultea a 'low' (conservador).
        Importante porque productos nuevos no tienen historia para WAPE."""
        tenant, product, warehouse, model = setup
        # NO seed accuracy
        call_command("recalibrate_confidence", tenant=tenant.id, verbosity=0)
        model.refresh_from_db()
        assert model.confidence_label == "low"

    def test_dry_run_does_not_modify(self, setup):
        """--dry-run muestra cambios sin aplicar."""
        tenant, product, warehouse, model = setup
        self._seed_accuracy(tenant, product, warehouse, [
            (50, 1), (50, 2), (50, 1),  # WAPE alto → very_low
        ])
        original_label = model.confidence_label
        call_command("recalibrate_confidence", tenant=tenant.id, dry_run=True, verbosity=0)
        model.refresh_from_db()
        assert model.confidence_label == original_label, "dry_run NO debe modificar DB"
