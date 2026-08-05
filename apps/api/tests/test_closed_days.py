"""
tests/test_closed_days.py — calendario del negocio y medición honesta.

Medido en Marbrava el 04/08/26 sobre 30 días de precisión real:
  - error medido:                   71,9% WAPE, sesgo +30,7%
  - sin domingos (local cerrado):   61,0% WAPE, sesgo +19,8%
  - sin domingos ni el 28-jul:      55,3% WAPE, sesgo +14,1%

Más de la mitad del sesgo eran días en que el local no abrió. El motor
pronosticaba demanda para esos días (sólo adaptive_ma y weighted_ma sabían de
días cerrados; ingredient_derived, theta y croston no) y después el sistema lo
anotaba como error del modelo.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product
from forecast.models import DailySales, ForecastAccuracy, ForecastModel, Forecast
from forecast.services import (
    get_business_closed_weekdays,
    _apply_closed_weekdays,
    _CLOSED_DOW_CACHE,
)

D = Decimal


@pytest.fixture(autouse=True)
def _limpiar_cache():
    """El cache es por proceso — entre tests hay que vaciarlo."""
    _CLOSED_DOW_CACHE.clear()
    yield
    _CLOSED_DOW_CACHE.clear()


def _ds(tenant, wh, product, day, qty):
    return DailySales.objects.create(
        tenant=tenant, product=product, warehouse=wh, date=day, qty_sold=D(str(qty)),
    )


def _semanas_operando(tenant, wh, product, hoy, semanas=10, cerrados=(6,)):
    """Historial donde el negocio opera todos los días salvo `cerrados`."""
    for i in range(1, semanas * 7 + 1):
        d = hoy - datetime.timedelta(days=i)
        if d.weekday() in cerrados:
            continue
        _ds(tenant, wh, product, d, 10)


def _horizonte(hoy, dias=7, qty="7.000"):
    """Pronóstico plano, como el que produce un algoritmo sin día-de-semana."""
    return [
        {
            "date": hoy + datetime.timedelta(days=i),
            "qty_predicted": D(qty),
            "lower_bound": D(qty) * D("0.7"),
            "upper_bound": D(qty) * D("1.3"),
        }
        for i in range(1, dias + 1)
    ]


# ── Detección a nivel de NEGOCIO ─────────────────────────────────────────────

@pytest.mark.django_db
def test_detecta_el_domingo_cerrado(tenant, warehouse, product):
    hoy = datetime.date.today()
    _semanas_operando(tenant, warehouse, product, hoy, cerrados=(6,))
    assert get_business_closed_weekdays(tenant.id, warehouse.id, today=hoy) == {6}


@pytest.mark.django_db
def test_detecta_dos_dias_cerrados(tenant, warehouse, product):
    """Restaurante que cierra domingo y lunes."""
    hoy = datetime.date.today()
    _semanas_operando(tenant, warehouse, product, hoy, cerrados=(0, 6))
    assert get_business_closed_weekdays(tenant.id, warehouse.id, today=hoy) == {0, 6}


@pytest.mark.django_db
def test_un_producto_de_baja_rotacion_NO_cierra_dias(tenant, warehouse, product):
    """LA SALVAGUARDA IMPORTANTE.

    El detector por-producto que ya existía (`detect_closed_weekdays`) marcaría
    como cerrados los días en que ESE producto no rota. Si lo usáramos para
    borrar pronósticos, borraríamos demanda real. Por eso la detección mira el
    negocio entero: si otro producto vendió ese día, el local estaba abierto.
    """
    hoy = datetime.date.today()
    # El negocio abre todos los días menos domingo…
    _semanas_operando(tenant, warehouse, product, hoy, cerrados=(6,))
    # …y este insumo sólo rota los martes.
    raro = Product.objects.create(tenant=tenant, name="Insumo lento", price=D("100"), is_active=True)
    for i in range(1, 71):
        d = hoy - datetime.timedelta(days=i)
        if d.weekday() == 1:
            _ds(tenant, warehouse, raro, d, 5)

    cerrados = get_business_closed_weekdays(tenant.id, warehouse.id, today=hoy)
    assert cerrados == {6}, "sólo el domingo; los otros días el local sí abrió"


@pytest.mark.django_db
def test_negocio_que_abre_todos_los_dias_no_tiene_cerrados(tenant, warehouse, product):
    hoy = datetime.date.today()
    _semanas_operando(tenant, warehouse, product, hoy, cerrados=())
    assert get_business_closed_weekdays(tenant.id, warehouse.id, today=hoy) == set()


@pytest.mark.django_db
def test_sin_datos_no_marca_nada(tenant, warehouse, product):
    """Bodega sin movimientos o tenant nuevo: preferimos no enmascarar nada
    antes que vaciar el pronóstico entero."""
    hoy = datetime.date.today()
    assert get_business_closed_weekdays(tenant.id, warehouse.id, today=hoy) == set()


# ── Máscara sobre el pronóstico ──────────────────────────────────────────────

@pytest.mark.django_db
def test_pone_en_cero_el_dia_cerrado(tenant, warehouse, product):
    hoy = datetime.date.today()
    fc = _horizonte(hoy)
    _apply_closed_weekdays(fc, {6})
    for f in fc:
        if f["date"].weekday() == 6:
            assert f["qty_predicted"] == D("0.000")
            assert f["lower_bound"] == D("0.000")
            assert f["upper_bound"] == D("0.000")


@pytest.mark.django_db
def test_preserva_la_masa_no_regala_demanda(tenant, warehouse, product):
    """Si sólo pusiéramos el domingo en 0, la semana caería a 6/7 del total
    y pasaríamos a SUB-comprar un 14%."""
    hoy = datetime.date.today()
    fc = _horizonte(hoy, dias=7, qty="7.000")
    antes = sum(f["qty_predicted"] for f in fc)
    _apply_closed_weekdays(fc, {6})
    despues = sum(f["qty_predicted"] for f in fc)
    assert abs(despues - antes) < D("0.01"), f"{antes} -> {despues}"


@pytest.mark.django_db
def test_es_idempotente_para_algoritmos_que_ya_saben(tenant, warehouse, product):
    """adaptive_ma y weighted_ma ya predicen 0 en días cerrados: no hay
    sobrante que repartir, así que aplicar la máscara no los infla."""
    hoy = datetime.date.today()
    fc = _horizonte(hoy)
    for f in fc:
        if f["date"].weekday() == 6:
            f["qty_predicted"] = D("0.000")
            f["lower_bound"] = D("0.000")
            f["upper_bound"] = D("0.000")
    copia = [dict(f) for f in fc]
    _apply_closed_weekdays(fc, {6})
    assert [f["qty_predicted"] for f in fc] == [f["qty_predicted"] for f in copia]


@pytest.mark.django_db
def test_aplicar_dos_veces_no_cambia_nada(tenant, warehouse, product):
    hoy = datetime.date.today()
    fc = _horizonte(hoy)
    _apply_closed_weekdays(fc, {6})
    primera = [f["qty_predicted"] for f in fc]
    _apply_closed_weekdays(fc, {6})
    assert [f["qty_predicted"] for f in fc] == primera


@pytest.mark.django_db
def test_sin_dias_abiertos_no_borra_nada(tenant, warehouse, product):
    """Guarda contra dividir por cero: si el horizonte cae entero en días
    cerrados, dejamos el pronóstico como está en vez de vaciarlo."""
    hoy = datetime.date.today()
    fc = _horizonte(hoy, dias=7)
    todos = {i for i in range(7)}
    _apply_closed_weekdays(fc, todos)
    assert all(f["qty_predicted"] > 0 for f in fc)


# ── Medición honesta ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_no_se_puntua_un_dia_sin_movimiento(tenant, warehouse, product, user):
    """El día del bloqueo de Hetzner (28-jul) no es un fallo del modelo."""
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="moving_avg", data_points=30,
    )
    Forecast.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, model=fm,
        forecast_date=ayer, qty_predicted=D("12.000"),
    )
    # No hay ninguna venta ese día en todo el negocio.
    call_command("track_forecast_accuracy", "--tenant", str(tenant.id), verbosity=0)
    assert not ForecastAccuracy.objects.filter(tenant=tenant, date=ayer).exists()


@pytest.mark.django_db
def test_si_hubo_movimiento_si_se_puntua(tenant, warehouse, product, user):
    """Control: un día normal se sigue midiendo (no rompimos la métrica)."""
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="moving_avg", data_points=30,
    )
    Forecast.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, model=fm,
        forecast_date=ayer, qty_predicted=D("12.000"),
    )
    _ds(tenant, warehouse, product, ayer, 10)
    call_command("track_forecast_accuracy", "--tenant", str(tenant.id), verbosity=0)
    fa = ForecastAccuracy.objects.get(tenant=tenant, date=ayer, product=product)
    assert fa.qty_actual == D("10.000")
    assert fa.qty_predicted == D("12.000")


@pytest.mark.django_db
def test_abrio_pero_no_vendio_ESTE_producto_si_se_puntua(tenant, warehouse, product, product_b):
    """La distinción que importa: el local abrió y vendió otras cosas, pero de
    este producto no salió ninguno. Eso SÍ es un error del modelo (predijo 12,
    se vendieron 0) y tiene que contar."""
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="moving_avg", data_points=30,
    )
    Forecast.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, model=fm,
        forecast_date=ayer, qty_predicted=D("12.000"),
    )
    _ds(tenant, warehouse, product, ayer, 0)     # este no vendió…
    _ds(tenant, warehouse, product_b, ayer, 9)   # …pero el local sí operó

    call_command("track_forecast_accuracy", "--tenant", str(tenant.id), verbosity=0)
    fa = ForecastAccuracy.objects.get(tenant=tenant, date=ayer, product=product)
    assert fa.qty_actual == D("0.000")
    assert fa.qty_predicted == D("12.000")


@pytest.mark.django_db
def test_dia_marcado_como_cerrado_no_se_puntua(tenant, warehouse, product):
    """Cierre puntual (bloqueo del servidor del 28-jul): `mark_closed_day` deja
    filas en 0 marcadas como no operativas. Existen filas, pero el día no cuenta."""
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="moving_avg", data_points=30,
    )
    Forecast.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, model=fm,
        forecast_date=ayer, qty_predicted=D("12.000"),
    )
    fila = _ds(tenant, warehouse, product, ayer, 0)
    DailySales.objects.filter(id=fila.id).update(is_stockout=True)

    call_command("track_forecast_accuracy", "--tenant", str(tenant.id), verbosity=0)
    assert not ForecastAccuracy.objects.filter(tenant=tenant, date=ayer).exists()


# ── Limpieza retroactiva ─────────────────────────────────────────────────────

def _precision_fantasma(tenant, warehouse, product, dia, pred="12.000"):
    return ForecastAccuracy.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, date=dia,
        qty_actual=D("0.000"), qty_predicted=D(pred), error=D(pred),
    )


@pytest.mark.django_db
def test_purga_dry_run_no_borra(tenant, warehouse, product):
    hoy = datetime.date.today()
    dia = hoy - datetime.timedelta(days=3)
    _precision_fantasma(tenant, warehouse, product, dia)
    call_command("purge_nonoperative_accuracy", "--tenant", str(tenant.id), verbosity=0)
    assert ForecastAccuracy.objects.filter(tenant=tenant, date=dia).exists()


@pytest.mark.django_db
def test_purga_borra_el_dia_fantasma_y_respeta_el_real(tenant, warehouse, product):
    hoy = datetime.date.today()
    fantasma = hoy - datetime.timedelta(days=3)
    real = hoy - datetime.timedelta(days=4)
    _precision_fantasma(tenant, warehouse, product, fantasma)
    _precision_fantasma(tenant, warehouse, product, real)
    _ds(tenant, warehouse, product, real, 8)  # ese día sí hubo movimiento

    call_command("purge_nonoperative_accuracy", "--tenant", str(tenant.id), "--apply", verbosity=0)

    assert not ForecastAccuracy.objects.filter(tenant=tenant, date=fantasma).exists()
    assert ForecastAccuracy.objects.filter(tenant=tenant, date=real).exists()
