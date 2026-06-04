"""
F (03/06/26) — sugerencias de compra: piso de seguridad por consumo REAL
(DailySales, incluye expansión de receta) en vez de solo SaleLine.

Bug real: se sugerían 274 "Syrup vainilla" con 0 consumo en 21 días. Las redes
de seguridad (cap 4×, skip) usaban SaleLine, que NO registra ingredientes (no
se venden, se consumen vía receta) → real_sold_30d=0 → escapaban el cap.

Fixes:
 1. SKIP ZOMBIE: producto que tuvo consumo (90d) pero 0 en 21d y el forecast
    sigue diciendo que se vende (>0.2/d) → no sugerir.
 2. CAP usa DailySales (consumo real) además de SaleLine → aplica a ingredientes.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from catalog.models import Product
from inventory.models import StockItem
from forecast.models import ForecastModel, Forecast, DailySales, SuggestionLine
from forecast.services import generate_suggestions

TODAY = date.today()


def _prod(tenant, name):
    return Product.objects.create(tenant=tenant, name=name, sku=f"SKU-{name}",
                                  price=Decimal("1000.00"), is_active=True)


def _model(tenant, warehouse, product):
    return ForecastModel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        algorithm="croston_sba", version=1, model_params={"avg_daily": "10.0"},
        metrics={"wape": 30.0}, data_points=400, is_active=True,
    )


def _forecasts(tenant, warehouse, product, model, qty, days=14, dts=2):
    for d in range(1, days + 1):
        Forecast.objects.create(
            tenant=tenant, warehouse=warehouse, product=product, model=model,
            forecast_date=TODAY + timedelta(days=d),
            qty_predicted=Decimal(str(qty)),
            lower_bound=Decimal(str(qty)) * Decimal("0.7"),
            upper_bound=Decimal(str(qty)) * Decimal("1.3"),
            days_to_stockout=dts, confidence=Decimal("70.00"),
        )


def _consumo(tenant, warehouse, product, qty_per_day, day_from, day_to):
    """DailySales (consumo real) entre day_from y day_to días atrás."""
    for d in range(day_from, day_to):
        DailySales.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            date=TODAY - timedelta(days=d), qty_sold=Decimal(str(qty_per_day)),
            forecast_only=False,
        )


def _suggested_ids(tenant):
    return set(SuggestionLine.objects.filter(suggestion__tenant=tenant)
               .values_list("product_id", flat=True))


def _line(tenant, pid):
    return SuggestionLine.objects.filter(suggestion__tenant=tenant, product_id=pid).first()


@pytest.mark.django_db
class TestZombieGuard:
    def test_zombie_no_se_sugiere(self, tenant, warehouse):
        """Tuvo consumo (40-50d atrás) pero 0 en 21d + forecast alto → NO sugerir."""
        p = _prod(tenant, "Syrup vainilla")
        m = _model(tenant, warehouse, p)
        _forecasts(tenant, warehouse, p, m, qty=10)            # forecast 10/d
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p,
                                 on_hand=Decimal("0"), avg_cost=Decimal("1000"))
        _consumo(tenant, warehouse, p, 5, 40, 50)              # consumo viejo, 0 reciente
        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        assert p.id not in _suggested_ids(tenant), "zombie no debe sugerirse"

    def test_ingrediente_activo_si_se_sugiere(self, tenant, warehouse):
        """Mismo forecast pero CON consumo reciente (últimos 21d) → SÍ sugerir."""
        p = _prod(tenant, "Leche")
        m = _model(tenant, warehouse, p)
        _forecasts(tenant, warehouse, p, m, qty=10)
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p,
                                 on_hand=Decimal("0"), avg_cost=Decimal("1000"))
        _consumo(tenant, warehouse, p, 9, 1, 25)               # consume ~9/d hasta hoy
        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        assert p.id in _suggested_ids(tenant), "ingrediente activo debe sugerirse"

    def test_ingrediente_nuevo_sin_historial_si_se_sugiere(self, tenant, warehouse):
        """Forecast alto pero SIN DailySales (ingrediente nuevo/derivado) → SÍ
        sugerir (no es zombie: nunca tuvo consumo que parar)."""
        p = _prod(tenant, "Cafe nuevo")
        m = _model(tenant, warehouse, p)
        _forecasts(tenant, warehouse, p, m, qty=10)
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p,
                                 on_hand=Decimal("0"), avg_cost=Decimal("1000"))
        # sin DailySales
        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        assert p.id in _suggested_ids(tenant), "ingrediente nuevo no debe saltarse"

    def test_cap_aplica_a_ingrediente_via_dailysales(self, tenant, warehouse):
        """Forecast enorme pero consumo real modesto → cap 4× sobre DailySales
        (sin SaleLine). Antes el cap no aplicaba a ingredientes (SaleLine=0)."""
        p = _prod(tenant, "Syrup caramelo")
        m = _model(tenant, warehouse, p)
        _forecasts(tenant, warehouse, p, m, qty=50)            # forecast 50/d (enorme)
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p,
                                 on_hand=Decimal("0"), avg_cost=Decimal("1000"))
        _consumo(tenant, warehouse, p, 1, 1, 30)               # 1/d → 29 unidades/30d
        generate_suggestions(tenant, TODAY, threshold=7, target_days=7)
        ln = _line(tenant, p.id)
        assert ln is not None, "tiene consumo reciente → se sugiere"
        # cap = 4 × consumo_30d (~29) = ~116. Sin el fix sería ~500+.
        assert float(ln.suggested_qty) <= 4 * 29 + 1, f"cap DailySales no aplicó: {ln.suggested_qty}"
