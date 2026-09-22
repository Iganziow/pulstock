"""
tests/test_lista_sin_muertos.py — la lista de compra sin productos muertos.

Mario no aprueba los pedidos. Medido sobre las 972 lineas sugeridas en
produccion desde el 1-ago-2026: el 35% son de productos que no consumieron NADA
en los 30 dias siguientes. Eso es lo que hace que la lista no se pueda mirar.

Las cantidades, en cambio, estan bien: contra el consumo de 30 dias la mediana
pide 1,2x. El problema no es CUANTO pide sino QUE productos entran.

El skip zombie que ya existia no los agarra: pide `avg_daily_raw > 0.2` para
actuar, asi que un producto chico que dejo de moverse se le escapa (el
pronostico dice 0,05/dia y la linea entra igual).

La regla nueva se eligio midiendo sobre esas 972 lineas:

    sin consumo en 21 dias -> calla 12% de las lineas, se equivoca en 11%
    sin consumo en 30 dias -> calla 11%, se equivoca en  4%   <- elegida
    sin consumo en 45 dias -> calla 10%, se equivoca en  4%
    sin consumo en 60 dias -> calla  6%, se equivoca en  6%

"Se equivoca" = la linea callada resulto usarse en los 30 dias siguientes.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from catalog.models import Product
from inventory.models import StockItem
from forecast.models import ForecastModel, Forecast, DailySales, SuggestionLine
from forecast.services import generate_suggestions

HOY = date.today()


def _prod(tenant, name):
    return Product.objects.create(tenant=tenant, name=name, sku="SKU-%s" % name,
                                  price=Decimal("1000.00"), is_active=True)


def _modelo(tenant, warehouse, product, avg="0.05"):
    """avg_daily chico a proposito: asi el skip zombie (que pide > 0,2) no aplica."""
    return ForecastModel.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        algorithm="croston_sba", version=1, model_params={"avg_daily": avg},
        metrics={"wape": 30.0}, data_points=400, is_active=True,
    )


def _pronosticos(tenant, warehouse, product, modelo, qty):
    for d in range(1, 15):
        Forecast.objects.create(
            tenant=tenant, warehouse=warehouse, product=product, model=modelo,
            forecast_date=HOY + timedelta(days=d), qty_predicted=Decimal(str(qty)),
            lower_bound=Decimal(str(qty)) * Decimal("0.7"),
            upper_bound=Decimal(str(qty)) * Decimal("1.3"),
            days_to_stockout=2, confidence=Decimal("70.00"),
        )


def _consumo(tenant, warehouse, product, qty, desde, hasta):
    for d in range(desde, hasta):
        DailySales.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            date=HOY - timedelta(days=d), qty_sold=Decimal(str(qty)),
            forecast_only=False,
        )


def _sugeridos(tenant):
    return set(SuggestionLine.objects.filter(suggestion__tenant=tenant)
               .values_list("product_id", flat=True))


def _escenario(tenant, warehouse, nombre, avg="0.05", qty="0.05"):
    p = _prod(tenant, nombre)
    m = _modelo(tenant, warehouse, p, avg=avg)
    _pronosticos(tenant, warehouse, p, m, qty)
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p,
                             on_hand=Decimal("0"), avg_cost=Decimal("1000"))
    return p


@pytest.mark.django_db
class TestListaSinMuertos:

    def test_el_que_no_se_movio_en_30_dias_no_entra(self, tenant, warehouse):
        """Se consumio hace 2 meses, nada desde entonces. El skip zombie no lo
        agarra porque su pronostico es de 0,05/dia."""
        p = _escenario(tenant, warehouse, "Obsecion")
        _consumo(tenant, warehouse, p, 1, 60, 70)
        generate_suggestions(tenant, HOY, threshold=7, target_days=7)
        assert p.id not in _sugeridos(tenant)

    def test_el_que_se_movio_hace_poco_si_entra(self, tenant, warehouse):
        """Control: un lento pero vivo tiene que seguir apareciendo."""
        p = _escenario(tenant, warehouse, "Torta de murta")
        _consumo(tenant, warehouse, p, 1, 3, 6)
        generate_suggestions(tenant, HOY, threshold=7, target_days=7)
        assert p.id in _sugeridos(tenant)

    def test_el_del_dia_29_todavia_entra(self, tenant, warehouse):
        """El borde: consumo dentro de la ventana de 30 dias, no se calla."""
        p = _escenario(tenant, warehouse, "Galleta")
        _consumo(tenant, warehouse, p, 1, 28, 29)
        generate_suggestions(tenant, HOY, threshold=7, target_days=7)
        assert p.id in _sugeridos(tenant)

    def test_el_producto_nuevo_sin_historia_si_entra(self, tenant, warehouse):
        """Sin consumo en 90 dias NO es un muerto: es un ingrediente nuevo o
        derivado que nunca tuvo movimiento que parar."""
        p = _escenario(tenant, warehouse, "Cafe nuevo")
        generate_suggestions(tenant, HOY, threshold=7, target_days=7)
        assert p.id in _sugeridos(tenant)

    def test_la_venta_directa_tambien_cuenta_como_movimiento(self, tenant, warehouse):
        """El movimiento se mide con el MAXIMO entre venta directa y consumo via
        receta, la misma base que usa el cap de seguridad. Un producto que se
        vende directo y no es ingrediente no puede quedar callado por eso."""
        p = _escenario(tenant, warehouse, "Te")
        _consumo(tenant, warehouse, p, 2, 1, 10)
        generate_suggestions(tenant, HOY, threshold=7, target_days=7)
        assert p.id in _sugeridos(tenant)
