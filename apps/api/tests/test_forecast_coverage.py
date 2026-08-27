"""
tests/test_forecast_coverage.py — el agujero que no se veía porque no se medía.

`track_forecast_accuracy` solo puntúa productos con fila en `Forecast`. Si un
producto deja de pronosticarse no aparece como error: desaparece del numerador
y del denominador, y el WAPE ni se mueve.

Caso real: `Leche deslactosada` estuvo 2,5 meses sin una sola fila de accuracy
vendiendo 200-1290 unidades diarias, y el tablero marcaba 6,7%.
"""
import datetime
from decimal import Decimal

import pytest

from catalog.models import Product
from forecast.coverage import find_coverage_gaps
from forecast.models import DailySales, Forecast, ForecastAccuracy, ForecastModel

D = Decimal
# Relativo a hoy, no una fecha fija. La version anterior clavaba el
# 20-ago-2026: los tests que llaman a find_coverage_gaps(today=HOY) seguian
# pasando, pero el que invoca el comando real usa date.today() por dentro, y
# empezo a fallar solo con que pasaran los dias. Un test con fecha quemada no
# se rompe cuando se rompe el codigo: se rompe cuando cambia el calendario.
HOY = datetime.date.today()


def _vender(tenant, warehouse, product, dias, qty="100"):
    """Ventas reales en `dias` días distintos dentro de la ventana."""
    for i in range(1, dias + 1):
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=HOY - datetime.timedelta(days=i), qty_sold=D(qty),
        )


def _modelo(tenant, warehouse, product):
    return ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="simple_avg", version=1, is_active=True,
        trained_at=datetime.datetime.now(datetime.timezone.utc),
    )


def _pronosticar(tenant, warehouse, product, fm, desde_offset=0, dias=7):
    for i in range(desde_offset, desde_offset + dias):
        Forecast.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, model=fm,
            forecast_date=HOY + datetime.timedelta(days=i),
            qty_predicted=D("100"), lower_bound=D("70"), upper_bound=D("130"),
        )


def _puntuar(tenant, warehouse, product, dias=5):
    for i in range(1, dias + 1):
        ForecastAccuracy.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=HOY - datetime.timedelta(days=i),
            qty_predicted=D("100"), qty_actual=D("100"), error=D("0"),
            abs_pct_error=D("0"), algorithm="simple_avg",
        )


@pytest.fixture
def otro_producto(db, tenant, category):
    return Product.objects.create(
        tenant=tenant, name="Leche deslactosada", sku="LD-1", category=category,
    )


@pytest.mark.django_db
class TestCoberturaDeForecast:
    def test_detecta_el_producto_que_se_vende_y_nadie_pronostica(
        self, tenant, warehouse, product, otro_producto,
    ):
        """EL BUG. `product` está cubierto; `otro_producto` vende y es invisible."""
        fm = _modelo(tenant, warehouse, product)
        _vender(tenant, warehouse, product, dias=10)
        _pronosticar(tenant, warehouse, product, fm)

        _vender(tenant, warehouse, otro_producto, dias=10, qty="365")  # sin forecast

        r = find_coverage_gaps(tenant.id, today=HOY)

        ciegos = {c["product_id"] for c in r["ciegos"]}
        assert otro_producto.id in ciegos, (
            "un producto que vende 365/dia sin pronostico tiene que saltar"
        )
        assert product.id not in ciegos

    def test_no_se_queja_de_productos_que_no_se_venden(
        self, tenant, warehouse, product, otro_producto,
    ):
        """Que no se pronostique algo que nadie compra es lo correcto, no un
        agujero. Si esto ladra por cada producto muerto, nadie lo mira."""
        fm = _modelo(tenant, warehouse, product)
        _vender(tenant, warehouse, product, dias=10)
        _pronosticar(tenant, warehouse, product, fm)
        # otro_producto no vendió nada

        r = find_coverage_gaps(tenant.id, today=HOY)
        assert r["ciegos"] == []

    def test_ordena_por_volumen(self, tenant, warehouse, product, otro_producto):
        """El primero de la lista tiene que ser el que más caro sale ignorar."""
        _vender(tenant, warehouse, product, dias=10, qty="5")
        _vender(tenant, warehouse, otro_producto, dias=10, qty="900")

        r = find_coverage_gaps(tenant.id, today=HOY)
        assert [c["product_id"] for c in r["ciegos"]][0] == otro_producto.id

    def test_un_pronostico_solo_a_futuro_ya_cuenta_como_cubierto(
        self, tenant, warehouse, otro_producto,
    ):
        """Las filas de Forecast se purgan, así que mirar fechas pasadas daría
        falsos positivos. Se mira de hoy en adelante a propósito."""
        fm = _modelo(tenant, warehouse, otro_producto)
        _vender(tenant, warehouse, otro_producto, dias=10)
        _pronosticar(tenant, warehouse, otro_producto, fm, desde_offset=1)

        r = find_coverage_gaps(tenant.id, today=HOY)
        assert otro_producto.id not in {c["product_id"] for c in r["ciegos"]}

    def test_distingue_ciego_de_sin_puntaje(self, tenant, warehouse, otro_producto):
        """El que se está recuperando (pronóstico desde hoy, todavía sin
        accuracy) no es la misma alarma que el que nadie mira."""
        fm = _modelo(tenant, warehouse, otro_producto)
        _vender(tenant, warehouse, otro_producto, dias=10)
        _pronosticar(tenant, warehouse, otro_producto, fm)
        # sin filas de ForecastAccuracy

        r = find_coverage_gaps(tenant.id, today=HOY)
        assert otro_producto.id not in {c["product_id"] for c in r["ciegos"]}
        assert otro_producto.id in {c["product_id"] for c in r["sin_puntaje"]}

    def test_cubierto_y_puntuado_no_aparece_en_ninguna_lista(
        self, tenant, warehouse, product,
    ):
        fm = _modelo(tenant, warehouse, product)
        _vender(tenant, warehouse, product, dias=10)
        _pronosticar(tenant, warehouse, product, fm)
        _puntuar(tenant, warehouse, product)

        r = find_coverage_gaps(tenant.id, today=HOY)
        assert r["ciegos"] == []
        assert r["sin_puntaje"] == []

    def test_no_mira_productos_de_otro_tenant(
        self, tenant, warehouse, product, otro_producto,
    ):
        """Un agujero ajeno no es una alarma propia."""
        _vender(tenant, warehouse, otro_producto, dias=10)
        r = find_coverage_gaps(tenant.id + 999, today=HOY)
        assert r["con_ventas"] == 0
        assert r["ciegos"] == []


@pytest.mark.django_db
class TestProductosMudos:
    """El agujero peor: el sistema cree que los mide y no los mide."""

    def test_detecta_al_que_tiene_pronostico_y_nunca_se_mide(
        self, tenant, warehouse, product, otro_producto,
    ):
        """EL CASO REAL. Leche deslactosada estuvo 2,5 meses así: pronóstico
        vigente, vendiendo 4.170 unidades cada 14 días, y ni una sola fila de
        accuracy. Como técnicamente tenía pronóstico, la alarma anterior lo
        daba por cubierto."""
        fm = _modelo(tenant, warehouse, otro_producto)
        _vender(tenant, warehouse, otro_producto, dias=10, qty="365")
        _pronosticar(tenant, warehouse, otro_producto, fm)
        # sin ninguna fila de ForecastAccuracy

        r = find_coverage_gaps(tenant.id, today=HOY)
        assert otro_producto.id not in {c["product_id"] for c in r["ciegos"]}, (
            "no es ciego: tiene pronóstico"
        )
        assert otro_producto.id in {m["product_id"] for m in r["mudos"]}, (
            "vende y tiene pronóstico pero no se mide hace 30 días: es mudo"
        )

    def test_el_que_si_se_mide_no_es_mudo(
        self, tenant, warehouse, product,
    ):
        fm = _modelo(tenant, warehouse, product)
        _vender(tenant, warehouse, product, dias=10)
        _pronosticar(tenant, warehouse, product, fm)
        _puntuar(tenant, warehouse, product)

        r = find_coverage_gaps(tenant.id, today=HOY)
        assert r["mudos"] == []

    def test_el_comando_FALLA_con_mudos(
        self, tenant, warehouse, otro_producto,
    ):
        """Tiene que romper, no avisar: un producto que el sistema cree medir
        y no mide da falsa tranquilidad, que es peor que no medirlo."""
        from django.core.management import call_command
        fm = _modelo(tenant, warehouse, otro_producto)
        _vender(tenant, warehouse, otro_producto, dias=10, qty="365")
        _pronosticar(tenant, warehouse, otro_producto, fm)

        with pytest.raises(RuntimeError, match="sin pronostico o sin medirse"):
            call_command("check_forecast_coverage", verbosity=0)


@pytest.mark.django_db
class TestComandoDeCobertura:
    def test_falla_cuando_hay_productos_invisibles(
        self, tenant, warehouse, otro_producto,
    ):
        """Es una alarma, no un informe: si termina en verde nadie la mira."""
        from django.core.management import call_command
        _vender(tenant, warehouse, otro_producto, dias=10, qty="365")

        with pytest.raises(RuntimeError, match="sin pronostico"):
            call_command("check_forecast_coverage", verbosity=0)

    def test_pasa_cuando_todo_esta_cubierto(self, tenant, warehouse, product):
        """Cubierto de verdad = se vende, se pronostica Y se mide. Sin lo
        tercero el sistema cree que lo mide y no lo mide, que es el agujero
        que costó 2,5 meses descubrir."""
        from django.core.management import call_command
        fm = _modelo(tenant, warehouse, product)
        _vender(tenant, warehouse, product, dias=10)
        _pronosticar(tenant, warehouse, product, fm)
        _puntuar(tenant, warehouse, product)

        call_command("check_forecast_coverage", verbosity=0)  # no debe lanzar
