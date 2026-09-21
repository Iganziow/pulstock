"""
tests/test_demanda_efectiva.py — se califica contra lo que se entrena.

Hasta el 20/09/26 había dos definiciones de "demanda" conviviendo:

  - `armar_serie_entrenamiento`: venta orgánica + merma (en restaurantes).
  - `track_forecast_accuracy`:   `qty_sold` pelado.

Medido en producción el 17-sep: el café tolva caturra entrenó con 628 g (128
vendidos + 500 de una merma cargada como "Salida") y se calificó contra 128. El
modelo predijo 485 para el día siguiente y la medición le cobró 279% de error por
acertarle razonablemente a la demanda con la que se le había enseñado.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast.models import DailySales, Forecast, ForecastAccuracy, ForecastModel
from forecast.services import demanda_efectiva

D = Decimal
HOY = datetime.date.today()
AYER = HOY - datetime.timedelta(days=1)


# ── la definición ────────────────────────────────────────────────────────────

def test_en_restaurante_la_merma_es_demanda():
    assert demanda_efectiva(True, D("128"), D("0"), D("500")) == D("628")


def test_en_retail_la_merma_es_perdida_no_demanda():
    assert demanda_efectiva(False, D("128"), D("0"), D("500")) == D("128")


def test_la_promocion_se_descuenta():
    assert demanda_efectiva(True, D("100"), D("30"), D("0")) == D("70")


def test_promocion_mayor_que_la_venta_se_acota():
    """Dato inconsistente: la promo no puede superar lo vendido."""
    assert demanda_efectiva(True, D("10"), D("40"), D("0")) == D("0")


def test_nunca_devuelve_negativo():
    assert demanda_efectiva(False, D("0"), D("0"), D("0")) == D("0")


def test_los_nulos_valen_cero():
    assert demanda_efectiva(True, D("5"), None, None) == D("5")


# ── el medidor ───────────────────────────────────────────────────────────────

def _escenario(tenant, warehouse, product, vendido, merma, predicho):
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="moving_avg", data_points=30,
    )
    Forecast.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, model=fm,
        forecast_date=AYER, qty_predicted=D(str(predicho)),
    )
    DailySales.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, date=AYER,
        qty_sold=D(str(vendido)), qty_lost=D(str(merma)),
    )
    call_command("track_forecast_accuracy", "--tenant", str(tenant.id), verbosity=0)
    return ForecastAccuracy.objects.get(tenant=tenant, date=AYER, product=product)


@pytest.mark.django_db
def test_el_cafe_se_califica_contra_628_no_contra_128(tenant, warehouse, product):
    """El caso del 17-sep, con los números reales."""
    tenant.business_type = "restaurant"
    tenant.save()
    fa = _escenario(tenant, warehouse, product, vendido=128, merma=500, predicho=485)
    assert fa.qty_actual == D("628.000")
    assert fa.error == D("-143.000")
    assert fa.abs_pct_error < D("25")  # antes daba 279%


@pytest.mark.django_db
def test_en_un_negocio_que_no_es_restaurante_no_cambia_nada(tenant, warehouse, product):
    """Control: donde la merma no es demanda, la medición queda como estaba."""
    tenant.business_type = "retail"
    tenant.save()
    fa = _escenario(tenant, warehouse, product, vendido=128, merma=500, predicho=485)
    assert fa.qty_actual == D("128.000")


@pytest.mark.django_db
def test_un_dia_sin_merma_mide_igual_que_siempre(tenant, warehouse, product):
    """El 99% de los días: sin merma, el número no se mueve."""
    tenant.business_type = "restaurant"
    tenant.save()
    fa = _escenario(tenant, warehouse, product, vendido=100, merma=0, predicho=120)
    assert fa.qty_actual == D("100.000")
    assert fa.error == D("20.000")
