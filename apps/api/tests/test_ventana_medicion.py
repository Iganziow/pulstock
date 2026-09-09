# -*- coding: utf-8 -*-
"""
tests/test_ventana_medicion.py — la ventana de medicion se ensancha hasta
juntar evidencia, y sin evidencia no se inventa un numero.

El problema (medido el 09/09/26 sobre los datos reales de Marbrava, cargados
en una base de pruebas: 190 modelos activos y 16.918 mediciones de 134 dias).
`recalibrate_confidence` corria con ventana fija de 14 dias y solo cuenta los
dias CON venta, asi que los productos de rotacion lenta nunca juntaban las 7
mediciones que exige el umbral. Resultado: 15 de 190 modelos tenian WAPE real
utilizable. Los otros 175 mostraban en pantalla -- y le entregaban al
kept-path -- el WAPE del backtest de la noche en que se entrenaron, congelado
hasta tres meses atras.

Con la escalera de ventanas (14, 30, 60, 90 dias), sobre esos mismos datos:

    modelos con medicion real     15  ->  76 de 190
    ventana que terminaron usando 14d: 15, 30d: 18, 60d: 28, 90d: 15
    de los 61 nuevos, el numero mostrado mejora en 39 y empeora en 15
    31 modelos cambian de etiqueta: 25 bajan y 6 suben
      (6 pasan de "high" a "very_low" y 1 de "very_high" a "very_low")

O sea que el fosil era mayormente PESIMISTA: la app se estaba subestimando.
Pero habia siete modelos prometiendo confianza alta sin ninguna evidencia.

Los 114 que siguen sin poder medirse venden tan poco que no juntan 7 dias con
venta ni en 90; para ellos la respuesta correcta no es otro numero sino decir
que no hay datos suficientes.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast.models import ForecastAccuracy, ForecastModel
from forecast.services import _precision_medida

D = Decimal
HOY = datetime.date.today()


def _modelo(tenant, product, warehouse, **kw):
    base = dict(algorithm="theta", version=1, is_active=True, model_params={},
                metrics={"wape": 146.5, "mae": 3.0}, data_points=60,
                demand_pattern="intermittent", confidence_label="high")
    base.update(kw)
    return ForecastModel.objects.create(tenant=tenant, product=product, warehouse=warehouse, **base)


def _midio(tenant, product, warehouse, dias_atras, pred, real):
    """Una medicion en un dia concreto."""
    ForecastAccuracy.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        date=HOY - datetime.timedelta(days=dias_atras),
        qty_predicted=D(str(pred)), qty_actual=D(str(real)),
        error=D(str(pred)) - D(str(real)), algorithm="theta")


class TestLaPrecisionMedida:
    def test_sin_mediciones_suficientes_no_hay_numero(self):
        assert _precision_medida({"wape": 146.5}) is None
        assert _precision_medida({"wape": 146.5, "wape_real": 29.0}) is None
        assert _precision_medida({"wape_real": 29.0, "wape_real_samples": 6}) is None
        assert _precision_medida({}) is None
        assert _precision_medida(None) is None

    def test_con_siete_mediciones_si(self):
        assert _precision_medida({"wape_real": 29.0, "wape_real_samples": 7}) == 29.0


@pytest.mark.django_db
class TestLaVentanaSeEnsancha:
    def test_un_producto_lento_ya_no_se_queda_sin_medicion(self, tenant, store, warehouse, product):
        """Ocho ventas repartidas en 80 dias: con la ventana fija de 14 no
        juntaba nada; ahora se mide con la de 90."""
        fm = _modelo(tenant, product, warehouse)
        for i, dia in enumerate([5, 14, 25, 33, 44, 55, 66, 77]):
            _midio(tenant, product, warehouse, dia, pred=10, real=5)

        call_command("recalibrate_confidence", days=14, tenant=tenant.id, verbosity=0)

        fm.refresh_from_db()
        assert fm.metrics["wape_real_samples"] == 8
        assert fm.metrics["wape_real_days"] == 90
        assert fm.metrics["wape_real"] == 100.0      # predice 10, vende 5
        assert _precision_medida(fm.metrics) == 100.0

    def test_un_producto_rapido_se_mide_con_la_ventana_corta(self, tenant, store, warehouse, product):
        """No se diluye en 90 dias a quien tiene datos frescos de sobra."""
        fm = _modelo(tenant, product, warehouse)
        for i in range(1, 13):
            _midio(tenant, product, warehouse, i, pred=10, real=8)
        for i in range(40, 60):                       # historia vieja y peor
            _midio(tenant, product, warehouse, i, pred=10, real=2)

        call_command("recalibrate_confidence", days=14, tenant=tenant.id, verbosity=0)

        fm.refresh_from_db()
        assert fm.metrics["wape_real_days"] == 14
        assert fm.metrics["wape_real"] == 25.0        # solo los 12 recientes

    def test_sin_ninguna_venta_no_se_inventa_nada(self, tenant, store, warehouse, product):
        """Los 114 productos que no juntan 7 mediciones ni en 90 dias."""
        fm = _modelo(tenant, product, warehouse)
        _midio(tenant, product, warehouse, 3, pred=10, real=0)   # dia sin venta: no cuenta

        call_command("recalibrate_confidence", days=14, tenant=tenant.id, verbosity=0)

        fm.refresh_from_db()
        assert "wape_real" not in (fm.metrics or {})
        assert _precision_medida(fm.metrics) is None
        assert fm.confidence_label == "high", "sin evidencia no se toca la etiqueta"

    def test_la_etiqueta_baja_cuando_la_evidencia_aparece(self, tenant, store, warehouse, product):
        """Los 7 modelos que prometian confianza alta sin datos."""
        fm = _modelo(tenant, product, warehouse, confidence_label="high")
        for dia in (4, 12, 20, 28, 36, 44, 52, 60):
            _midio(tenant, product, warehouse, dia, pred=100, real=10)   # 900% de error

        call_command("recalibrate_confidence", days=14, tenant=tenant.id, verbosity=0)

        fm.refresh_from_db()
        assert fm.metrics["wape_real"] == 900.0
        assert fm.confidence_label != "high", "con 900%% de error real no puede seguir en alta"


@pytest.mark.django_db
class TestLoQueVeElUsuario:
    def test_la_api_no_muestra_el_backtest_como_precision(self, tenant, store, warehouse, product):
        from forecast.services import get_product_forecasts
        _modelo(tenant, product, warehouse, metrics={"wape": 146.5, "mae": 3.0})
        data = get_product_forecasts(tenant.id, [warehouse.id])
        fila = next((r for r in data["results"] if r["product_id"] == product.id), None)
        assert fila is not None
        assert fila["display_wape"] is None
        assert fila["precision_medida"] is False
        assert fila["wape"] == 146.5, "el backtest se sigue exponiendo, pero aparte"
