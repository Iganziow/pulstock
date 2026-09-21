"""
tests/test_dia_sin_operacion.py — un día cerrado no es un día de demanda cero.

Caso real, medido en producción el 20-sep-2026: Marbrava cerró el viernes 18 y
el sábado 19 por Fiestas Patrias. `aggregate_daily_sales` no escribe filas para
días sin venta, así que el relleno de ceros de `armar_serie_entrenamiento` los
metió como dos ceros. `seasonal_naive`, que predice cada día futuro copiando el
mismo día de la semana anterior, publicó para el viernes 25 y el sábado 26:

    Leche entera          jueves 1001,5 ml  →  viernes 0,0  sábado 0,0
    Café tolva caturra    jueves  553,9 g   →  viernes 0,0  sábado 0,0

Los dos productos más grandes del local, en cero, el fin de semana. La
sugerencia de compra del lunes venía vacía para ambos.
"""
import datetime
from decimal import Decimal

import pytest

from forecast.models import DailySales
from forecast.services import armar_serie_entrenamiento, dias_sin_operacion

D = Decimal
LUNES = datetime.date(2026, 6, 1)  # 2026-06-01 es lunes


def _dia(n):
    return LUNES + datetime.timedelta(days=n)


def _vender(tenant, warehouse, product, dias, qty="100"):
    for n in dias:
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=_dia(n), qty_sold=D(qty),
        )


@pytest.fixture
def local(db, tenant, warehouse, product):
    """12 semanas de ventas de lunes a sábado; los domingos el local cierra."""
    abiertos = [n for n in range(84) if _dia(n).weekday() != 6]
    _vender(tenant, warehouse, product, abiertos)
    return abiertos


# ── el helper ────────────────────────────────────────────────────────────────

def test_encuentra_el_dia_sin_ninguna_venta(local, tenant, warehouse):
    """Un día sin una sola venta en todo el local sale en la lista."""
    DailySales.objects.filter(date=_dia(30)).delete()  # miércoles cerrado
    sin_operar = dias_sin_operacion(tenant.id, warehouse.id, _dia(0), _dia(83))
    assert _dia(30) in sin_operar


def test_un_producto_sin_venta_no_cierra_el_local(local, tenant, warehouse, product_b):
    """Que UN producto no se venda no dice nada: se mide el local entero."""
    _vender(tenant, warehouse, product_b, [1])  # product_b vende un solo día
    sin_operar = dias_sin_operacion(
        tenant.id, warehouse.id, _dia(0), _dia(83), closed_dows={6},
    )
    assert sin_operar == set()


def test_los_domingos_cerrados_se_dejan_como_estan(local, tenant, warehouse):
    """El domingo tiene su propio mecanismo (`_apply_closed_weekdays`)."""
    sin_operar = dias_sin_operacion(
        tenant.id, warehouse.id, _dia(0), _dia(83), closed_dows={6},
    )
    assert sin_operar == set()


def test_sin_el_filtro_de_domingos_aparecen_todos(local, tenant, warehouse):
    """Guarda de la guarda: son 12 domingos, el 14% del período."""
    sin_operar = dias_sin_operacion(tenant.id, warehouse.id, _dia(0), _dia(83))
    assert len(sin_operar) == 12
    assert all(d.weekday() == 6 for d in sin_operar)


def test_demasiados_dias_sin_operar_es_un_problema_de_datos(db, tenant, warehouse, product):
    """Una bodega casi sin movimiento no es un calendario de cierres."""
    _vender(tenant, warehouse, product, [0, 40, 83])
    assert dias_sin_operacion(tenant.id, warehouse.id, _dia(0), _dia(83)) == set()


def test_periodo_vacio_no_explota(db, tenant, warehouse):
    assert dias_sin_operacion(tenant.id, warehouse.id, _dia(10), _dia(9)) == set()


# ── la serie de entrenamiento ────────────────────────────────────────────────

def test_el_feriado_sale_de_la_serie(local, tenant, warehouse, product):
    """El día cerrado no entra como cero: no entra."""
    feriado = _dia(74)  # viernes
    DailySales.objects.filter(date=feriado).delete()
    serie = armar_serie_entrenamiento(tenant, product, warehouse.id, _dia(83), 10)
    fechas = {d for d, _ in serie["raw_series"]}
    assert feriado not in fechas
    assert serie["sin_operacion"] == {feriado}


def test_el_domingo_sigue_entrando_como_cero(local, tenant, warehouse, product):
    """Si el domingo desapareciera, `_apply_closed_weekdays` no tendría qué repartir."""
    serie = armar_serie_entrenamiento(tenant, product, warehouse.id, _dia(83), 10)
    domingos = [(d, q) for d, q in serie["raw_series"] if d.weekday() == 6]
    assert domingos, "los domingos tienen que seguir en la serie"
    assert all(float(q) == 0 for _, q in domingos)


def test_la_serie_sigue_terminando_en_hoy(local, tenant, warehouse, product):
    """Todos los algoritmos anclan el horizonte en el último punto de la serie.

    Si `today` se cayera con el resto de los días sin venta, el pronóstico
    saldría corrido hacia atrás para TODOS los productos.
    """
    hoy = _dia(83)
    serie = armar_serie_entrenamiento(tenant, product, warehouse.id, hoy, 10)
    assert serie["raw_series"][-1][0] == hoy


def test_sin_dias_cerrados_la_serie_no_cambia(local, tenant, warehouse, product):
    """Sin cierres puntuales, el recorte no toca nada."""
    serie = armar_serie_entrenamiento(tenant, product, warehouse.id, _dia(83), 10)
    assert serie["sin_operacion"] == set()
    assert len(serie["raw_series"]) == 84


# ── la regresión que importa ─────────────────────────────────────────────────

def test_seasonal_naive_ya_no_publica_cero_el_viernes(local, tenant, warehouse, product):
    """El caso de Marbrava: cerrar un viernes no puede vaciar el viernes siguiente."""
    from forecast.engine.algorithms.seasonal_naive import SeasonalNaive

    # El ultimo viernes antes de `hoy`: es el que seasonal_naive copia para
    # el viernes del horizonte. Un viernes mas atras no probaria nada.
    feriado = _dia(81)
    assert feriado.weekday() == 4
    DailySales.objects.filter(date=feriado).delete()

    hoy = _dia(83)
    serie = armar_serie_entrenamiento(tenant, product, warehouse.id, hoy, 10)
    salida = SeasonalNaive().forecast(serie["cleaned"], horizon_days=7)
    viernes = [
        f for f in salida["forecasts"]
        if f["date"].weekday() == 4 and f["date"] > hoy
    ]
    assert viernes, "el horizonte tiene que incluir un viernes"
    assert all(float(f["qty_predicted"]) > 0 for f in viernes), (
        "el viernes siguiente al feriado quedó en cero: "
        + str([(str(f["date"]), float(f["qty_predicted"])) for f in viernes])
    )


def test_sin_el_recorte_el_viernes_queda_en_cero(local, tenant, warehouse, product, monkeypatch):
    """La otra mitad del test de arriba: que el bug existía de verdad.

    Con el recorte apagado (el comportamiento anterior al 20-sep-2026) la
    misma serie y el mismo algoritmo publican cero el viernes siguiente.
    """
    from forecast import services
    from forecast.engine.algorithms.seasonal_naive import SeasonalNaive

    feriado = _dia(81)
    DailySales.objects.filter(date=feriado).delete()
    monkeypatch.setattr(services, "dias_sin_operacion", lambda *a, **k: set())

    hoy = _dia(83)
    serie = armar_serie_entrenamiento(tenant, product, warehouse.id, hoy, 10)
    assert feriado in {d for d, _ in serie["raw_series"]}
    salida = SeasonalNaive().forecast(serie["cleaned"], horizon_days=7)
    viernes = [
        f for f in salida["forecasts"]
        if f["date"].weekday() == 4 and f["date"] > hoy
    ]
    assert viernes and all(float(f["qty_predicted"]) == 0 for f in viernes)


# ── un solo criterio para los dos lados (21/09/26) ───────────────────────────
#
# `business_operated_on` (el medidor, desde el 04/08/26) y `dias_sin_operacion`
# (el entrenamiento, desde el 20/09/26) respondían la misma pregunta con reglas
# distintas. El 28-jul-2026 se cayó el servidor y quedaron 176 filas en cero,
# todas marcadas como quiebre: el medidor salteaba el día y el entrenamiento se
# lo comía como un cero real. Es el único día de los 435 con filas en que las
# dos reglas daban respuestas distintas.

def _dia_de_servidor_caido(tenant, warehouse, product, product_b, dia):
    """Filas en cero para todo el catálogo, todas marcadas como quiebre."""
    DailySales.objects.filter(date=dia).delete()
    for p in (product, product_b):
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse, date=dia,
            qty_sold=D("0"), is_stockout=True,
        )


def test_el_dia_del_servidor_caido_no_conto_como_operado(
    local, tenant, warehouse, product, product_b,
):
    from forecast.services import business_operated_on

    caido = _dia(40)
    _dia_de_servidor_caido(tenant, warehouse, product, product_b, caido)
    assert not business_operated_on(tenant.id, caido)
    assert caido in dias_sin_operacion(tenant.id, warehouse.id, _dia(0), _dia(83))


def test_el_dia_del_servidor_caido_sale_de_la_serie(
    local, tenant, warehouse, product, product_b,
):
    """Lo que estaba mal: ese día entrenaba a todos los modelos con un cero."""
    caido = _dia(40)
    _dia_de_servidor_caido(tenant, warehouse, product, product_b, caido)
    serie = armar_serie_entrenamiento(tenant, product, warehouse.id, _dia(83), 10)
    assert caido not in {d for d, _ in serie["raw_series"]}


def test_abrio_y_no_vendio_este_producto_si_cuenta(
    local, tenant, warehouse, product, product_b,
):
    """La distinción que importa: filas en cero pero SIN marcar quiebre es un
    día abierto en que no se vendió, y eso sí es demanda cero de verdad."""
    from forecast.services import business_operated_on

    abierto = _dia(41)
    DailySales.objects.filter(date=abierto).delete()
    DailySales.objects.create(
        tenant=tenant, product=product_b, warehouse=warehouse, date=abierto,
        qty_sold=D("0"), is_stockout=False,
    )
    assert business_operated_on(tenant.id, abierto)
    assert abierto not in dias_sin_operacion(tenant.id, warehouse.id, _dia(0), _dia(83))


def test_los_dos_lados_responden_siempre_lo_mismo(
    local, tenant, warehouse, product, product_b,
):
    """La garantía de que no se vuelvan a desalinear."""
    from forecast.services import business_operated_on

    _dia_de_servidor_caido(tenant, warehouse, product, product_b, _dia(40))
    DailySales.objects.filter(date=_dia(50)).delete()          # sin una sola fila
    sin_operar = dias_sin_operacion(tenant.id, warehouse.id, _dia(0), _dia(83))
    for i in range(84):
        d = _dia(i)
        if d.weekday() == 6:
            continue  # los domingos los maneja `_apply_closed_weekdays`
        assert business_operated_on(tenant.id, d) == (d not in sin_operar), d
