"""
Tests Fase 5: WAPE real (post-hoc) guardado y expuesto en respuestas API.

BUG (Chocolate Premium en Marbrava prod)
========================================
- algorithm: croston_sba
- confidence_label: "high"
- confidence_reason: "WAPE real 29% en últimos 14 días (5 comparaciones)"
- metrics.wape: 146.5

Contradicción visual: la confianza dice "high" basada en WAPE real 29%, pero
metrics.wape muestra 146% del backtest del entrenamiento. Misma fuente -
dos números opuestos.

FIX
===
recalibrate_confidence guarda `metrics.wape_real` (+ samples + days) cuando
hay datos suficientes de ForecastAccuracy. La API expone wape_real en
get_product_forecasts y get_product_detail. Helper `display_wape` prioriza
wape_real sobre wape (backtest).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product, Unit
from forecast.models import ForecastAccuracy, ForecastModel


@pytest.fixture
def units_simple(db, tenant):
    u, _ = Unit.objects.get_or_create(
        tenant=tenant, code="UN",
        defaults={"name": "Unidad", "family": "COUNT"},
    )
    return u


@pytest.fixture
def chocolate_premium_like(db, tenant, units_simple, warehouse_a):
    """Producto con modelo de backtest malo pero WAPE real bueno (caso real)."""
    p = Product.objects.create(
        tenant=tenant, name="Chocolate Premium-like",
        unit_obj=units_simple, is_active=True,
    )
    fm = ForecastModel.objects.create(
        tenant=tenant, product=p, warehouse=warehouse_a,
        algorithm="croston_sba", version=1, is_active=True,
        model_params={"avg_daily": "5"},
        # Backtest dio mal (intermittent forecast), pero en produccion el
        # modelo predice ok-ish (variabilidad baja en los ultimos 14 dias).
        metrics={"mae": 1.5, "wape": 146.5, "mape": 60, "rmse": 2},
        data_points=300, demand_pattern="lumpy",
        confidence_label="low", confidence_reason="(stale)",
    )
    return p, fm


@pytest.mark.django_db
class TestWapeRealStorage:

    def test_recalibrate_stores_wape_real_in_metrics(
        self, tenant, units_simple, warehouse_a, chocolate_premium_like,
    ):
        """Despues de recalibrate, metrics debe tener wape_real, wape_real_days
        y wape_real_samples sin tocar `wape` original (del backtest)."""
        p, fm = chocolate_premium_like
        today = date.today()

        # Generar ForecastAccuracy: 5 dias con error bajo
        for i in range(1, 6):
            d = today - timedelta(days=i)
            ForecastAccuracy.objects.create(
                tenant=tenant, product=p, warehouse=warehouse_a,
                date=d,
                qty_predicted=Decimal("5"), qty_actual=Decimal("5"),
                error=Decimal("0"), abs_pct_error=Decimal("0"),
                was_stockout=False,
            )
        # Un dia con error mayor para llegar a un WAPE != 0
        ForecastAccuracy.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a,
            date=today - timedelta(days=6),
            qty_predicted=Decimal("5"), qty_actual=Decimal("7"),
            error=Decimal("-2"), abs_pct_error=Decimal("28.6"),
            was_stockout=False,
        )

        call_command("recalibrate_confidence", tenant=tenant.id, days=14, verbosity=0)

        fm.refresh_from_db()
        assert fm.metrics is not None
        assert "wape_real" in fm.metrics, (
            f"metrics debe tener wape_real, got {list(fm.metrics.keys())}"
        )
        # El backtest WAPE se preserva
        assert fm.metrics["wape"] == 146.5
        # El real esta guardado y es bajo (mayoria de errores son 0)
        assert fm.metrics["wape_real"] < 20
        assert fm.metrics["wape_real_samples"] == 6
        assert fm.metrics["wape_real_days"] == 14

    def test_no_wape_real_when_insufficient_accuracy_data(
        self, tenant, units_simple, warehouse_a, chocolate_premium_like,
    ):
        """Sin ForecastAccuracy, wape_real no se agrega."""
        p, fm = chocolate_premium_like
        original_metrics = dict(fm.metrics)

        call_command("recalibrate_confidence", tenant=tenant.id, days=14, verbosity=0)

        fm.refresh_from_db()
        # metrics debe quedar igual (sin wape_real agregado)
        assert "wape_real" not in fm.metrics
        assert fm.metrics["wape"] == original_metrics["wape"]

    def test_confidence_label_updates_with_wape_real(
        self, tenant, units_simple, warehouse_a, chocolate_premium_like,
    ):
        """El label debe pasar de 'low' a 'high' cuando WAPE real es excelente."""
        p, fm = chocolate_premium_like
        today = date.today()

        # WAPE real ~0% (excelente)
        for i in range(1, 8):
            ForecastAccuracy.objects.create(
                tenant=tenant, product=p, warehouse=warehouse_a,
                date=today - timedelta(days=i),
                qty_predicted=Decimal("5"), qty_actual=Decimal("5"),
                error=Decimal("0"), abs_pct_error=Decimal("0"),
                was_stockout=False,
            )

        call_command("recalibrate_confidence", tenant=tenant.id, days=14, verbosity=0)

        fm.refresh_from_db()
        assert fm.confidence_label == "high"
        assert "WAPE real" in fm.confidence_reason


@pytest.mark.django_db
class TestWapeRealExposedInAPI:
    """Verifica que la API expone wape_real y display_wape al frontend."""

    def test_get_product_forecasts_includes_wape_real(
        self, tenant, units_simple, warehouse_a, chocolate_premium_like,
    ):
        from forecast.services import get_product_forecasts
        p, fm = chocolate_premium_like
        fm.metrics = {
            **fm.metrics,
            "wape_real": 29.0,
            "wape_real_days": 14,
            "wape_real_samples": 5,
        }
        fm.save(update_fields=["metrics"])

        data = get_product_forecasts(tenant.id, [warehouse_a.id])
        row = next(r for r in data["results"] if r["product_id"] == p.id)

        assert row["wape"] == 146.5, "wape del backtest preservado"
        assert row["wape_real"] == 29.0, "wape_real expuesto"
        assert row["wape_real_samples"] == 5
        # display_wape prioriza wape_real
        assert row["display_wape"] == 29.0

    def test_get_product_forecasts_display_wape_falls_back_to_backtest(
        self, tenant, units_simple, warehouse_a, chocolate_premium_like,
    ):
        """Si no hay wape_real, display_wape cae al wape del backtest."""
        from forecast.services import get_product_forecasts
        p, fm = chocolate_premium_like
        # fm.metrics NO tiene wape_real

        data = get_product_forecasts(tenant.id, [warehouse_a.id])
        row = next(r for r in data["results"] if r["product_id"] == p.id)

        assert row["wape_real"] is None
        assert row["display_wape"] == 146.5  # cae al wape del backtest

    def test_get_product_detail_includes_display_wape_and_confidence(
        self, tenant, units_simple, warehouse_a, chocolate_premium_like,
    ):
        from forecast.services import get_product_detail
        p, fm = chocolate_premium_like
        fm.metrics = {**fm.metrics, "wape_real": 29.0}
        fm.confidence_label = "high"
        fm.confidence_reason = "WAPE real 29% en últimos 14 días (5 comparaciones)"
        fm.save()

        data = get_product_detail(tenant.id, p.id, [warehouse_a.id])
        assert data is not None
        assert data["model"]["confidence_label"] == "high"
        assert "29%" in data["model"]["confidence_reason"]
        assert data["model"]["display_wape"] == 29.0
