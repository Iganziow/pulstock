"""
F (03/06/26) — safety stock probabilístico por nivel de servicio.
Reemplaza el buffer plano %: SS = z(α) × σ(RMSE) × √(cobertura).
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from catalog.models import Product
from inventory.models import StockItem
from forecast.models import ForecastModel, Forecast, SuggestionLine
from forecast.services import generate_suggestions, _z_for_service_level

TODAY = date.today()


def test_z_for_service_level():
    assert abs(_z_for_service_level(0.95) - 1.6449) < 0.01
    assert abs(_z_for_service_level(0.99) - 2.3263) < 0.01
    assert abs(_z_for_service_level(0.90) - 1.2816) < 0.01
    # monótono: más servicio → más z
    assert _z_for_service_level(0.99) > _z_for_service_level(0.95) > _z_for_service_level(0.90)
    # clamp
    assert _z_for_service_level(0.4) == _z_for_service_level(0.50)


def _prod(tenant, name):
    return Product.objects.create(tenant=tenant, name=name, sku=f"SKU-{name}",
                                  price=Decimal("1000.00"), is_active=True)


def _model(tenant, warehouse, product, rmse):
    return ForecastModel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        algorithm="croston_sba", version=1, model_params={"avg_daily": "5.0"},
        metrics={"wape": 30.0, "rmse": rmse}, data_points=400, is_active=True,
    )


def _forecasts(tenant, warehouse, product, model, qty=5):
    for d in range(1, 15):
        Forecast.objects.create(
            tenant=tenant, warehouse=warehouse, product=product, model=model,
            forecast_date=TODAY + timedelta(days=d),
            qty_predicted=Decimal(str(qty)),
            lower_bound=Decimal("0"), upper_bound=Decimal(str(qty * 1.3)),
            days_to_stockout=2, confidence=Decimal("70.00"),
        )


def _stock0(tenant, warehouse, product):
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=product,
                             on_hand=Decimal("0"), avg_cost=Decimal("600"))


@pytest.mark.django_db
class TestServiceLevelSafetyStock:
    def test_higher_uncertainty_more_safety_stock(self, tenant, warehouse):
        """Mismo forecast, mayor σ (RMSE) → mayor cantidad sugerida (más SS)."""
        p_hi = _prod(tenant, "Incierto")
        p_lo = _prod(tenant, "Estable")
        _forecasts(tenant, warehouse, p_hi, _model(tenant, warehouse, p_hi, rmse=10.0))
        _forecasts(tenant, warehouse, p_lo, _model(tenant, warehouse, p_lo, rmse=2.0))
        _stock0(tenant, warehouse, p_hi); _stock0(tenant, warehouse, p_lo)

        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)

        hi = SuggestionLine.objects.filter(suggestion__tenant=tenant, product=p_hi).first()
        lo = SuggestionLine.objects.filter(suggestion__tenant=tenant, product=p_lo).first()
        assert hi and lo, "ambos deben sugerirse"
        assert hi.suggested_qty > lo.suggested_qty, (
            f"mayor incertidumbre debe pedir más colchón: {hi.suggested_qty} vs {lo.suggested_qty}")

    def test_rmse_zero_no_crash_y_sugiere(self, tenant, warehouse):
        """Sin RMSE confiable → cae al buffer previo, sigue sugiriendo (no crash)."""
        p = _prod(tenant, "SinRMSE")
        _forecasts(tenant, warehouse, p, _model(tenant, warehouse, p, rmse=0.0))
        _stock0(tenant, warehouse, p)
        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        assert SuggestionLine.objects.filter(suggestion__tenant=tenant, product=p).exists()
