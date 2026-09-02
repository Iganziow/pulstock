# -*- coding: utf-8 -*-
"""
tests/test_calidad_por_peso.py — que el termometro mida el cuerpo, no la ropa.

El WAPE global de un catalogo real esta dominado por productos que casi no
venden. Medido en Marbrava el 02/09/26 sobre 30 dias:

    todo (lo que reportabamos)   192 productos   sesgo +23%   WAPE 63%
    nucleo (90% de la venta)      13 productos   sesgo +13%   WAPE 51%

Esos 12 puntos no eran el modelo: eran 152 productos que aportan el 3% de la
venta, 38 de los cuales no vendieron NADA en el mes. El 89% de las mediciones
de `adaptive_ma` se toman contra un real de cero.

Lo que se fija aca es que la separacion exista y sea honesta en ambos
sentidos: que el nucleo no se contamine con la cola, y que la cola no
desaparezca (sigue siendo visible en `total`).
"""
import datetime
from decimal import Decimal

import pytest

from forecast.coverage import calidad_por_peso
from forecast.models import ForecastAccuracy

D = Decimal


@pytest.fixture
def hoy():
    return datetime.date(2026, 9, 2)


def _medir(tenant, product, warehouse, fecha, pred, real, alg="adaptive_ma"):
    return ForecastAccuracy.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, date=fecha,
        qty_predicted=D(str(pred)), qty_actual=D(str(real)),
        error=D(str(pred)) - D(str(real)), algorithm=alg,
    )


@pytest.mark.django_db
class TestSeparaLoQuePesa:
    def test_el_nucleo_no_se_contamina_con_la_cola(
        self, tenant, warehouse, product, product_b, hoy,
    ):
        """EL CASO REAL. Un producto que vende mucho y se predice bien; otro
        que no vende nada y se predice mal. El WAPE global se dispara; el del
        nucleo tiene que quedarse donde corresponde."""
        for i in range(1, 11):
            f = hoy - datetime.timedelta(days=i)
            # nucleo: vende 100, se predice 110 (10% de error)
            _medir(tenant, product, warehouse, f, 110, 100)
            # cola: no vende nada, se predice 5 (error infinito)
            _medir(tenant, product_b, warehouse, f, 5, 0)

        q = calidad_por_peso(tenant.id, today=hoy)

        assert q["nucleo"]["n_productos"] == 1
        assert q["nucleo"]["wape_pct"] == pytest.approx(10.0, abs=0.5), (
            "el WAPE del nucleo se contamino con la cola"
        )
        assert q["total"]["wape_pct"] > q["nucleo"]["wape_pct"], (
            "el total deberia verse peor: incluye la cola"
        )

    def test_la_cola_no_desaparece(self, tenant, warehouse, product, product_b, hoy):
        """Separar no puede volverse esconder: la cola sigue contando en
        `total`, que es lo que evita que un producto se vuelva invisible --
        el agujero original que motivo todo este modulo."""
        for i in range(1, 6):
            f = hoy - datetime.timedelta(days=i)
            _medir(tenant, product, warehouse, f, 100, 100)
            _medir(tenant, product_b, warehouse, f, 9, 0)

        q = calidad_por_peso(tenant.id, today=hoy)
        assert q["cola"]["n_mediciones"] == 5
        assert q["total"]["n_mediciones"] == 10
        assert q["nucleo"]["n_mediciones"] == 5

    def test_pareto_corta_donde_se_acumula_la_fraccion(
        self, tenant, warehouse, product, product_b, hoy,
    ):
        """El nucleo se define por volumen acumulado, no por umbral fijo de
        unidades: asi significa lo mismo en una cafeteria que en una
        ferreteria."""
        f = hoy - datetime.timedelta(days=1)
        _medir(tenant, product, warehouse, f, 95, 95)     # 95% de la venta
        _medir(tenant, product_b, warehouse, f, 5, 5)     # 5%

        q = calidad_por_peso(tenant.id, today=hoy, fraccion=0.90)
        assert q["nucleo"]["n_productos"] == 1, "el corte de Pareto no aplico"
        assert q["cola"]["n_productos"] == 1


@pytest.mark.django_db
class TestBordes:
    def test_sin_mediciones_no_revienta(self, tenant, hoy):
        q = calidad_por_peso(tenant.id, today=hoy)
        assert q["total"]["n_mediciones"] == 0
        assert q["nucleo"]["wape_pct"] is None

    def test_catalogo_entero_en_cero_no_divide_por_cero(
        self, tenant, warehouse, product, hoy,
    ):
        """Un negocio cerrado toda la ventana. No puede tumbar la corrida."""
        for i in range(1, 4):
            _medir(tenant, product, warehouse, hoy - datetime.timedelta(days=i), 3, 0)
        q = calidad_por_peso(tenant.id, today=hoy)
        assert q["total"]["wape_pct"] is None
        assert q["nucleo"]["n_productos"] == 0, (
            "un producto sin una sola venta no puede entrar al nucleo"
        )

    def test_el_comando_nocturno_sigue_corriendo(
        self, tenant, warehouse, product, hoy,
    ):
        """La alarma no puede caerse por el reporte nuevo."""
        from django.core.management import call_command
        for i in range(1, 4):
            _medir(tenant, product, warehouse, hoy - datetime.timedelta(days=i), 10, 10)
        try:
            call_command("check_forecast_coverage", tenant=tenant.id, verbosity=0)
        except RuntimeError:
            pass  # la alarma puede fallar por cobertura; lo que importa es que no explote
