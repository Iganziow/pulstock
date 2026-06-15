"""
Recalibración de confianza para demanda intermitente (Mario 15/06/26).

Problema: el WAPE día-a-día es estructuralmente alto en demanda esporádica
(dulces que venden 1/mes o ráfagas), aunque Croston capture bien la TASA.
Eso mandaba TODOS los intermitentes a 'low/very_low' y la etiqueta no servía.

Fix: para intermittent/lumpy la confianza se calcula con MASE (¿le gana al
naive? = ¿la tasa es confiable?), no con WAPE. Smooth sigue con WAPE.

Cubre los DOS caminos que setean la etiqueta:
  1. compute_confidence_label (entrenamiento nocturno)
  2. recalibrate_confidence (post-hoc, corre vía track_forecast_accuracy)
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product
from core.models import Warehouse
from forecast.models import ForecastModel, ForecastAccuracy
from forecast.services import compute_confidence_label


class TestConfidenceIntermittentByMase:
    """Camino 1: compute_confidence_label usa MASE para intermittent/lumpy."""

    def test_high_when_mase_low_and_enough_history(self):
        label, reason = compute_confidence_label(
            data_points=433, error_pct=157.0, demand_pattern="intermittent", mase=0.754)
        assert label == "high", reason
        assert "MASE" in reason

    def test_medium_when_beats_naive(self):
        label, _ = compute_confidence_label(
            data_points=417, error_pct=146.0, demand_pattern="intermittent", mase=0.815)
        assert label == "medium"

    def test_low_when_near_naive(self):
        label, _ = compute_confidence_label(
            data_points=232, error_pct=114.0, demand_pattern="intermittent", mase=1.184)
        assert label == "low"

    def test_very_low_when_worse_than_naive(self):
        label, _ = compute_confidence_label(
            data_points=200, error_pct=120.0, demand_pattern="intermittent", mase=2.5)
        assert label == "very_low"

    def test_lumpy_uses_same_mase_path(self):
        label, _ = compute_confidence_label(
            data_points=100, error_pct=300.0, demand_pattern="lumpy", mase=0.7)
        assert label == "high"

    def test_high_wape_does_not_drag_intermittent_down(self):
        """El punto del fix: WAPE 150% NO debe tirar a 'low' si la tasa
        (MASE) es buena. Antes esto daba very_low."""
        label, _ = compute_confidence_label(
            data_points=400, error_pct=150.0, demand_pattern="intermittent", mase=0.75)
        assert label == "high"

    @pytest.mark.parametrize("bad_mase", [None, 0, -1, 5, 333, 666, 999])
    def test_very_low_when_mase_invalid_or_zero_volume(self, bad_mase):
        """Productos casi sin ventas (naive≈0 → MASE explota a 333/666) o
        sin métrica → very_low (no se puede confiar en la tasa)."""
        label, _ = compute_confidence_label(
            data_points=400, error_pct=150.0, demand_pattern="intermittent", mase=bad_mase)
        assert label == "very_low"

    def test_intermittent_never_very_high(self):
        """Tope 'high' para intermitentes — nunca very_high."""
        label, _ = compute_confidence_label(
            data_points=500, error_pct=10.0, demand_pattern="intermittent", mase=0.1)
        assert label == "high"


class TestConfidenceSmoothUnchanged:
    """Regresión: smooth sigue con WAPE, sin cambios."""

    def test_smooth_very_high(self):
        label, _ = compute_confidence_label(
            data_points=200, error_pct=15.0, demand_pattern="smooth")
        assert label == "very_high"

    def test_smooth_high(self):
        label, _ = compute_confidence_label(
            data_points=90, error_pct=30.0, demand_pattern="smooth")
        assert label == "high"

    def test_smooth_low_when_high_wape(self):
        label, _ = compute_confidence_label(
            data_points=10, error_pct=120.0, demand_pattern="smooth")
        assert label == "low"

    def test_smooth_ignores_mase_arg(self):
        """Smooth no usa MASE aunque se lo pasen."""
        label, _ = compute_confidence_label(
            data_points=200, error_pct=15.0, demand_pattern="smooth", mase=99.0)
        assert label == "very_high"


@pytest.mark.django_db
class TestRecalibrateKeepsIntermittentOnMase:
    """Camino 2: recalibrate_confidence NO debe tirar a very_low un
    intermitente con buena tasa solo porque su WAPE real es alto."""

    def _seed_bad_wape(self, tenant, product, warehouse):
        """Siembra accuracy con WAPE día-a-día altísimo (típico intermitente)."""
        today = date.today()
        rows = [(2, 0), (2, 0), (0, 3), (1, 0), (2, 0), (0, 2), (1, 0)]
        for i, (pred, actual) in enumerate(rows):
            ForecastAccuracy.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=today - timedelta(days=i + 1),
                qty_predicted=Decimal(str(pred)), qty_actual=Decimal(str(actual)),
                error=Decimal(str(pred - actual)),
                abs_pct_error=None, algorithm="croston_sba", was_stockout=False,
            )

    def test_intermittent_stays_trustworthy_despite_bad_wape(self, tenant, store):
        warehouse = Warehouse.objects.create(tenant=tenant, store=store, name="W-int")
        product = Product.objects.create(
            tenant=tenant, name="Brownie", price=Decimal("2500"), is_active=True)
        model = ForecastModel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            algorithm="croston_sba", version=1, is_active=True,
            model_params={}, metrics={"mase": 0.75, "wape": 150.0, "rmse": 1.2},
            data_points=120, demand_pattern="intermittent",
            confidence_label="very_low", confidence_reason="viejo",
        )
        self._seed_bad_wape(tenant, product, warehouse)

        call_command("recalibrate_confidence", tenant=tenant.id, verbosity=0)
        model.refresh_from_db()
        # Con WAPE real altísimo, el comando viejo daba very_low. Ahora, al ser
        # intermitente con MASE 0.75 y 120 días, debe quedar 'high'.
        assert model.confidence_label == "high", model.confidence_reason
        assert "MASE" in model.confidence_reason

    def test_smooth_still_uses_real_wape(self, tenant, store):
        """Regresión: smooth sigue calibrando por WAPE real."""
        warehouse = Warehouse.objects.create(tenant=tenant, store=store, name="W-sm")
        product = Product.objects.create(
            tenant=tenant, name="Cafe del dia", price=Decimal("1500"), is_active=True)
        model = ForecastModel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            algorithm="adaptive_ma", version=1, is_active=True,
            model_params={}, metrics={"mase": 0.5, "wape": 10.0},
            data_points=120, demand_pattern="smooth",
            confidence_label="medium", confidence_reason="viejo",
        )
        # Accuracy con WAPE real bajo (~6%) → debería ir a high
        today = date.today()
        for i, (pred, actual) in enumerate([(10, 10), (12, 11), (8, 9), (10, 11)]):
            ForecastAccuracy.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=today - timedelta(days=i + 1),
                qty_predicted=Decimal(str(pred)), qty_actual=Decimal(str(actual)),
                error=Decimal(str(pred - actual)), abs_pct_error=None,
                algorithm="adaptive_ma", was_stockout=False,
            )
        call_command("recalibrate_confidence", tenant=tenant.id, verbosity=0)
        model.refresh_from_db()
        assert model.confidence_label == "high", model.confidence_reason
        assert "WAPE real" in model.confidence_reason
